"""
LogWriter component for the brain-memory service.
Writes log-type information to file system and updates graph indexes.

v3: Separates detailed logs (file storage) from high-level cognition (graph storage).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from server.storage.graph import GraphStore

logger = logging.getLogger(__name__)


class LogWriter:
    """
    Writes log-type information to file system and updates graph entity indexes.

    Logs are stored in: BASE_DIR/{category_subdir}/{YYYY-MM-DD}.md
    Graph entities are updated with: last_log_date, log_path properties.
    """

    BASE_DIR = "/root/.openclaw/workspace/memory/logs"

    # category → subdirectory mapping
    CATEGORY_DIRS = {
        "log_diet": "diet",
        "log_exercise": "exercise",
        "log_interview": "interview",
        "log_trading": "trading",
        "log_learning": "learning",
        "log_general": "general",
    }

    def __init__(self, graph: GraphStore) -> None:
        self.graph = graph

    async def write_log(
        self,
        category: str,
        message: str,
        target_entity: Optional[str],
        tenant_id: str,
        user_id: str,
        timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Write a log entry to file and update graph index.

        Args:
            category: Log category (log_diet, log_exercise, etc.)
            message: Log message content
            target_entity: Name of graph entity to update (e.g., "减肥计划")
            tenant_id: Tenant ID
            user_id: User ID
            timestamp: Optional timestamp (defaults to now in UTC+8)

        Returns:
            Dict with keys: file_path, log_date, target_entity_updated
        """
        if category not in self.CATEGORY_DIRS:
            logger.warning("Unknown log category '%s', using 'log_general'", category)
            category = "log_general"

        # Use Beijing time (UTC+8)
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        # Convert to Beijing time for file naming
        from datetime import timedelta
        beijing_time = timestamp + timedelta(hours=8)
        date_str = beijing_time.strftime("%Y-%m-%d")
        time_str = beijing_time.strftime("%H:%M")

        # Determine file path
        subdir = self.CATEGORY_DIRS[category]
        log_dir = Path(self.BASE_DIR) / subdir
        log_dir.mkdir(parents=True, exist_ok=True)

        file_path = log_dir / f"{date_str}.md"

        # Append log entry
        is_new_file = not file_path.exists()
        with open(file_path, "a", encoding="utf-8") as f:
            if is_new_file:
                # Write header for new file
                category_name = self._get_category_display_name(category)
                f.write(f"# {category_name} {date_str}\n\n")

            # Write log entry
            f.write(f"- {time_str} {message}\n")

        logger.info(
            "Wrote log entry to %s (category=%s, target=%s)",
            file_path, category, target_entity
        )

        # Update graph entity index if target_entity is specified
        entity_updated = False
        if target_entity:
            entity_updated = await self._update_graph_index(
                target_entity, str(log_dir), date_str, tenant_id, user_id
            )

        return {
            "file_path": str(file_path),
            "log_date": date_str,
            "target_entity_updated": entity_updated,
        }

    async def _update_graph_index(
        self,
        entity_name: str,
        log_path: str,
        date: str,
        tenant_id: str,
        user_id: str,
    ) -> bool:
        """
        Update graph entity's log index properties.

        Sets:
            - last_log_date: Latest log date
            - log_path: Directory path for logs

        Returns:
            True if entity was found and updated, False otherwise
        """
        try:
            # Find entity by name
            nodes = await self.graph.find_nodes_by_name(entity_name, tenant_id, user_id)
            if not nodes:
                logger.warning(
                    "Target entity '%s' not found in graph, skipping index update",
                    entity_name
                )
                return False

            # Update the first matching node
            node = nodes[0]
            updates = {
                "properties": {
                    **(node.properties or {}),
                    "last_log_date": date,
                    "log_path": log_path,
                }
            }

            await self.graph.update_node(node.id, updates)
            logger.info(
                "Updated graph index for entity '%s' (last_log_date=%s, log_path=%s)",
                entity_name, date, log_path
            )
            return True

        except Exception as e:
            logger.error("Failed to update graph index for entity '%s': %s", entity_name, e)
            return False

    @staticmethod
    def _get_category_display_name(category: str) -> str:
        """Get display name for log category."""
        display_names = {
            "log_diet": "饮食记录",
            "log_exercise": "运动记录",
            "log_interview": "面试记录",
            "log_trading": "交易记录",
            "log_learning": "学习记录",
            "log_general": "日志记录",
        }
        return display_names.get(category, "日志记录")
