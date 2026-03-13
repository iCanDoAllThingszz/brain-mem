"""
Consolidator engine component for the brain-memory service.
Corresponds to the sleep consolidation mechanism in the human brain.
Transfers buffered memory units into the long-term Neo4j graph.

v2: Adapted for encoder v2 (action/aliases_to_add/tag merge) + per-unit archive.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from server.activity_log import log_event
from server.engine.llm_client import call_llm_json
from server.models.node import Node
from server.models.relation import Relation
from server.storage.buffer import EncoderBuffer
from server.storage.graph import GraphStore
from server.storage.tag_dict import TagDict

logger = logging.getLogger(__name__)

_PATTERN_SYSTEM = """\
You are a pattern discovery engine for a memory system. \
Analyze the provided memory fragments and identify cross-event patterns, \
recurring themes, or emerging trends.

Return ONLY valid JSON:
{
  "patterns": ["Pattern description 1", "Pattern description 2"],
  "conflicts": ["Conflict description"]
}
"""

_ORPHAN_RELATION_SYSTEM = """\
You are a knowledge graph relationship builder. Given orphan nodes (no relationships) \
and connected nodes, suggest relationships.

Rules:
- Only suggest clearly implied relationships. Do NOT guess.
- Relation types: UPPER_SNAKE_CASE (e.g., WEIGHS, INTERESTED_IN, PART_OF).
- Maximum 1 relationship per orphan. Keep descriptions SHORT (under 10 words).
- If no clear relationship exists for an orphan, skip it.

Return ONLY valid JSON:
{"suggested_relations": [{"from_name": "A", "to_name": "B", "type": "REL", "description": "short"}]}
"""


class Consolidator:
    """Memory consolidator — sleep consolidation mechanism."""

    def __init__(self, graph: GraphStore, tag_dict: TagDict, buffer: EncoderBuffer) -> None:
        self.graph = graph
        self.tag_dict = tag_dict
        self.buffer = buffer

    async def consolidate(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """Execute sleep consolidation: buffer -> long-term graph."""
        stats: Dict[str, Any] = {
            "nodes_created": 0, "nodes_updated": 0, "nodes_merged": 0,
            "relations_created": 0, "patterns_discovered": [], "conflicts_found": [],
            "units_processed": 0, "units_skipped": 0,
        }

        units = self.buffer.read_unarchived(tenant_id, user_id)
        if not units:
            logger.info("No unarchived units for tenant=%s user=%s", tenant_id, user_id)
            # Still run orphan repair even with no new units
            try:
                orphan_rels = await self._repair_orphans(tenant_id, user_id, {})
                stats["relations_created"] += orphan_rels
            except Exception as e:
                logger.warning("Orphan repair failed: %s", e)
            return stats

        valid_units = [u for u in units if float(u.get("importance", 0)) >= 3.0]
        stats["units_skipped"] = len(units) - len(valid_units)

        log_event("consolidation_start",
            f"Processing {len(valid_units)} units (skipped {stats['units_skipped']} low-imp)",
            {"tenant": tenant_id, "total": len(units), "valid": len(valid_units)})

        name_to_id: Dict[str, str] = {}

        for unit in valid_units:
            unit_id = unit.get("id", "")
            try:
                for entity in unit.get("entities", []):
                    node_id, created, merged = await self._upsert_entity(
                        entity, tenant_id, user_id, unit)
                    if node_id:
                        name_to_id[entity.get("name", "")] = node_id
                        fn = entity.get("final_name")
                        if fn and fn != entity.get("name"):
                            name_to_id[fn] = node_id
                        if created:
                            stats["nodes_created"] += 1
                        elif merged:
                            stats["nodes_merged"] += 1
                        else:
                            stats["nodes_updated"] += 1

                for rel_data in unit.get("relations", []):
                    if await self._upsert_relation(rel_data, name_to_id, tenant_id, user_id, unit):
                        stats["relations_created"] += 1

                stats["units_processed"] += 1
                if unit_id:
                    self.buffer.archive_by_id(unit_id)
            except Exception as e:
                logger.error("Failed to consolidate unit %s: %s", unit_id, e)

        # Archive low-importance units too
        for unit in units:
            if float(unit.get("importance", 0)) < 3.0:
                uid = unit.get("id", "")
                if uid:
                    self.buffer.archive_by_id(uid)

        patterns, conflicts = await self._discover_patterns(valid_units)
        stats["patterns_discovered"] = patterns
        stats["conflicts_found"] = conflicts

        # Step 5.5: Repair orphan nodes (suggest missing relations)
        try:
            orphan_rels = await self._repair_orphans(tenant_id, user_id, name_to_id)
            stats["relations_created"] += orphan_rels
        except Exception as e:
            logger.warning("Orphan repair failed: %s", e)

        try:
            await self.graph.apply_decay(tenant_id, user_id)
        except Exception as e:
            logger.error("apply_decay failed: %s", e)

        log_event("consolidation_complete",
            f"created={stats['nodes_created']} updated={stats['nodes_updated']} "
            f"merged={stats['nodes_merged']} rels={stats['relations_created']}",
            stats)
        logger.info("Consolidation complete: %s", stats)
        return stats

    # ------------------------------------------------------------------
    # Entity upsert (v2: respects action field)
    # ------------------------------------------------------------------

    async def _upsert_entity(
        self, entity: Dict[str, Any], tenant_id: str, user_id: str, unit: Dict[str, Any],
    ) -> Tuple[Optional[str], bool, bool]:
        """Upsert entity based on encoder v2 action field. Returns (node_id, created, merged)."""
        name = entity.get("name", "").strip()
        if not name:
            return None, False, False

        action = entity.get("action", "create")
        existing_id = entity.get("existing_id")
        aliases = entity.get("aliases_to_add", [])
        tags = entity.get("tags", [])

        # --- merge / update ---
        if action in ("merge", "update") and existing_id:
            try:
                updates: Dict[str, Any] = {"updated_at": datetime.utcnow().isoformat()}
                summary = entity.get("summary_update") or entity.get("summary")
                if summary:
                    updates["summary"] = summary
                props = entity.get("properties_update") or entity.get("properties")
                if props:
                    updates["properties"] = props
                await self.graph.update_node(existing_id, updates)
                if tags:
                    await self.graph.merge_tags(existing_id, tags)
                if aliases:
                    await self.graph.add_aliases(existing_id, aliases)

                log_event("consolidation_entity", f"{action}: {name} -> {existing_id[:8]}", {
                    "action": action, "aliases": aliases[:3], "tags": tags[:3]})
                return existing_id, False, action == "merge"
            except Exception as e:
                logger.warning("%s failed for '%s': %s", action, name, e)
                return existing_id, False, False

        # --- create ---
        # Double-check to prevent duplicates
        try:
            matches = await self.graph.find_nodes_by_name(name, tenant_id, user_id)
            if not matches:
                matches = await self.graph.find_nodes_by_alias(name, tenant_id, user_id)
        except Exception:
            matches = []

        if matches:
            eid = matches[0].id
            updates = {"updated_at": datetime.utcnow().isoformat()}
            summary = entity.get("summary_update") or entity.get("summary")
            if summary:
                updates["summary"] = summary
            try:
                await self.graph.update_node(eid, updates)
                if tags:
                    await self.graph.merge_tags(eid, tags)
                if aliases:
                    await self.graph.add_aliases(eid, aliases)
            except Exception as e:
                logger.warning("update existing failed: %s", e)
            return eid, False, False

        # Actually create
        try:
            zone = entity.get("zone", "semantic")
            if zone not in {"semantic", "episodic", "procedural", "emotional"}:
                zone = "semantic"
            emotion_type = unit.get("emotion_type", "neutral")
            if emotion_type not in {"joy", "sadness", "anger", "fear", "surprise", "neutral"}:
                emotion_type = "neutral"

            node = Node(
                name=name, aliases=aliases, tags=tags,
                summary=entity.get("summary", ""), zone=zone,
                importance=float(unit.get("importance", 5.0)),
                emotional_tag={
                    "type": emotion_type,
                    "intensity": float(unit.get("emotional_intensity", 0)),
                },
                source_sessions=[unit.get("session_id", "")],
                properties=entity.get("properties", {}),
            )
            created_node = await self.graph.create_node(node, tenant_id, user_id)
            log_event("consolidation_entity", f"create: {name}", {
                "action": "create", "node_id": created_node.id[:8], "tags": tags[:3]})
            return created_node.id, True, False
        except Exception as e:
            logger.error("create_node failed for '%s': %s", name, e)
            return None, False, False

    # ------------------------------------------------------------------
    # Relation upsert
    # ------------------------------------------------------------------

    async def _upsert_relation(
        self, rel_data: Dict[str, Any], name_to_id: Dict[str, str],
        tenant_id: str, user_id: str, unit: Dict[str, Any],
    ) -> bool:
        """Create a relation if it doesn't already exist."""
        from_name = rel_data.get("from_name", "")
        to_name = rel_data.get("to_name", "")
        rel_type = rel_data.get("type", "RELATED_TO").upper().replace(" ", "_")

        from_id = name_to_id.get(from_name)
        to_id = name_to_id.get(to_name)
        if not from_id or not to_id:
            return False

        try:
            existing_rels = await self.graph.get_relations(from_id)
            for rel in existing_rels:
                if rel.to_id == to_id and rel.type == rel_type:
                    return False
        except Exception:
            pass

        try:
            relation = Relation(
                from_id=from_id, to_id=to_id, type=rel_type,
                description=rel_data.get("description", ""),
                valid_from=datetime.utcnow(),
                source_session=unit.get("session_id", ""),
            )
            await self.graph.create_relation(relation)
            return True
        except Exception as e:
            logger.error("create_relation failed (%s->%s %s): %s", from_name, to_name, rel_type, e)
            return False

    # ------------------------------------------------------------------
    # Pattern discovery
    # ------------------------------------------------------------------

    async def _discover_patterns(
        self, units: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[str]]:
        """Use LLM to discover cross-event patterns."""
        if len(units) < 3:
            return [], []
        fragments = "\n".join(
            f"- [{u.get('timestamp', '')[:10]}] {u.get('message', '')[:200]}"
            for u in units[-30:]
        )
        try:
            result = await call_llm_json(_PATTERN_SYSTEM, f"Memory fragments:\n{fragments}")
            return result.get("patterns", []), result.get("conflicts", [])
        except Exception as e:
            logger.warning("Pattern discovery failed: %s", e)
            return [], []

    async def _repair_orphans(
        self, tenant_id: str, user_id: str, name_to_id: Dict[str, str]
    ) -> int:
        """Find orphan nodes and suggest missing relationships via LLM."""
        all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
        
        orphans = []
        connected = []
        for node in all_nodes:
            rels = await self.graph.get_relations(node.id)
            info = {"name": node.name, "tags": node.tags, "summary": node.summary or "", "id": node.id}
            if not rels:
                orphans.append(info)
            else:
                connected.append(info)
        
        if not orphans or not connected:
            return 0
        
        orphan_text = "\n".join(f"- {o['name']} (tags={o['tags']}, summary={o['summary'][:60]})" for o in orphans)
        connected_text = "\n".join(f"- {c['name']} (tags={c['tags']}, summary={c['summary'][:60]})" for c in connected[:20])
        
        user_prompt = f"Orphan nodes (no relationships):\n{orphan_text}\n\nConnected nodes:\n{connected_text}"
        
        try:
            result = await call_llm_json(_ORPHAN_RELATION_SYSTEM, user_prompt, temperature=0.1)
        except Exception as e:
            logger.warning("Orphan relation suggestion failed: %s", e)
            return 0
        
        # Build name→id map for all nodes
        all_name_to_id = {n.name: n.id for n in all_nodes}
        all_name_to_id.update(name_to_id)
        
        created = 0
        for rel in result.get("suggested_relations", []):
            from_name = rel.get("from_name", "")
            to_name = rel.get("to_name", "")
            rel_type = rel.get("type", "RELATED_TO").upper().replace(" ", "_")
            
            from_id = all_name_to_id.get(from_name)
            to_id = all_name_to_id.get(to_name)
            if not from_id or not to_id:
                continue
            
            try:
                relation = Relation(
                    from_id=from_id, to_id=to_id, type=rel_type,
                    description=rel.get("description", ""),
                    valid_from=datetime.utcnow(),
                    source_session="consolidator-orphan-repair",
                )
                await self.graph.create_relation(relation)
                created += 1
                log_event("consolidation_orphan_repair", f"{from_name} -{rel_type}-> {to_name}", {
                    "from": from_name, "to": to_name, "type": rel_type,
                })
            except Exception as e:
                logger.warning("Failed to create orphan relation %s->%s: %s", from_name, to_name, e)
        
        if created:
            logger.info("Repaired %d orphan relationships", created)
        return created
