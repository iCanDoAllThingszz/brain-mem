"""
ProspectiveChecker engine component for the brain-memory service.
Checks for prospective memory triggers that need to be activated.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List

from server.storage.graph import GraphStore

logger = logging.getLogger(__name__)


class ProspectiveChecker:
    """
    Prospective memory checker — monitors and triggers pending reminders.

    Checks for time-based and event-based triggers that should be activated.
    """

    def __init__(self, graph: GraphStore) -> None:
        self.graph = graph

    async def check_time_triggers(
        self,
        tenant_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Check for time-based triggers that are due.

        Args:
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            List of triggered reminders with keys: node_id, action, trigger_value
        """
        # Get current time in Beijing timezone (UTC+8)
        beijing_tz = timezone(timedelta(hours=8))
        current_time = datetime.now(beijing_tz)

        # Query graph for all pending time triggers
        query = """
        MATCH (n:MemoryNode)
        WHERE n.tenant_id = $tenant_id
          AND n.user_id = $user_id
          AND n.zone = 'procedural'
          AND '提醒' IN n.tags
          AND n.properties CONTAINS 'trigger_type'
        RETURN n
        """

        driver = self.graph._ensure_connected()
        triggered = []

        async with driver.session() as session:
            result = await session.run(query, tenant_id=tenant_id, user_id=user_id)
            records = await result.data()

            for record in records:
                node_props = dict(record["n"])

                # Parse properties JSON
                import json
                properties = json.loads(node_props.get("properties", "{}"))

                trigger_type = properties.get("trigger_type")
                trigger_value = properties.get("trigger_value")
                status = properties.get("status", "pending")
                action = properties.get("action", "")
                node_id = node_props.get("id")

                # Only check time triggers that are pending
                if trigger_type != "time" or status != "pending":
                    continue

                # Parse trigger time
                try:
                    trigger_time = datetime.fromisoformat(trigger_value.replace("+08:00", ""))
                    # Make it timezone-aware if not already
                    if trigger_time.tzinfo is None:
                        trigger_time = trigger_time.replace(tzinfo=beijing_tz)

                    # Check if trigger time has passed
                    if current_time >= trigger_time:
                        triggered.append({
                            "node_id": node_id,
                            "action": action,
                            "trigger_value": trigger_value,
                            "trigger_type": "time",
                        })

                        # Update status to completed
                        await self._update_trigger_status(node_id, "completed")
                        logger.info(
                            "Time trigger activated: %s (trigger_time=%s, current_time=%s)",
                            action, trigger_time, current_time
                        )
                except Exception as e:
                    logger.warning("Failed to parse time trigger '%s': %s", trigger_value, e)

        return triggered

    async def check_event_triggers(
        self,
        tenant_id: str,
        user_id: str,
        current_query: str,
    ) -> List[Dict[str, Any]]:
        """
        Check for event-based triggers that match the current query.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            current_query: Current user query

        Returns:
            List of triggered reminders with keys: node_id, action, trigger_value
        """
        # Query graph for all pending event triggers
        query = """
        MATCH (n:MemoryNode)
        WHERE n.tenant_id = $tenant_id
          AND n.user_id = $user_id
          AND n.zone = 'procedural'
          AND '提醒' IN n.tags
          AND n.properties CONTAINS 'trigger_type'
        RETURN n
        """

        driver = self.graph._ensure_connected()
        triggered = []

        async with driver.session() as session:
            result = await session.run(query, tenant_id=tenant_id, user_id=user_id)
            records = await result.data()

            for record in records:
                node_props = dict(record["n"])

                # Parse properties JSON
                import json
                properties = json.loads(node_props.get("properties", "{}"))

                trigger_type = properties.get("trigger_type")
                trigger_value = properties.get("trigger_value", "")
                status = properties.get("status", "pending")
                action = properties.get("action", "")
                node_id = node_props.get("id")

                # Only check event triggers that are pending
                if trigger_type != "event" or status != "pending":
                    continue

                # Simple keyword matching (case-insensitive)
                query_lower = current_query.lower()
                trigger_lower = trigger_value.lower()

                if trigger_lower in query_lower or query_lower in trigger_lower:
                    triggered.append({
                        "node_id": node_id,
                        "action": action,
                        "trigger_value": trigger_value,
                        "trigger_type": "event",
                    })

                    # Update status to completed
                    await self._update_trigger_status(node_id, "completed")
                    logger.info(
                        "Event trigger activated: %s (trigger=%s, query=%s)",
                        action, trigger_value, current_query[:50]
                    )

        return triggered

    async def _update_trigger_status(self, node_id: str, new_status: str) -> None:
        """
        Update the status of a trigger node.

        Args:
            node_id: Node ID
            new_status: New status (completed, expired, etc.)
        """
        query = """
        MATCH (n:MemoryNode {id: $node_id})
        SET n.properties = apoc.convert.toJson(
            apoc.convert.fromJsonMap(n.properties) + {status: $new_status}
        )
        RETURN n
        """

        driver = self.graph._ensure_connected()
        async with driver.session() as session:
            try:
                await session.run(query, node_id=node_id, new_status=new_status)
            except Exception as e:
                # Fallback: manual JSON update if APOC is not available
                logger.warning("APOC not available, using manual JSON update: %s", e)

                # Fetch current properties
                fetch_query = "MATCH (n:MemoryNode {id: $node_id}) RETURN n.properties as props"
                result = await session.run(fetch_query, node_id=node_id)
                record = await result.single()

                if record:
                    import json
                    props = json.loads(record["props"])
                    props["status"] = new_status

                    # Update with new properties
                    update_query = "MATCH (n:MemoryNode {id: $node_id}) SET n.properties = $props"
                    await session.run(update_query, node_id=node_id, props=json.dumps(props))
