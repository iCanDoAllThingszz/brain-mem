"""
Consolidator engine component for the brain-memory service.
Corresponds to the sleep consolidation mechanism in the human brain.
Transfers buffered memory units into the long-term Neo4j graph.

v2: Adapted for encoder v2 (action/aliases_to_add/tag merge) + per-unit archive.
"""

from __future__ import annotations

import json
import logging
import random
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

# ---------------------------------------------------------------------------
# Minimal hardcoded rules (fallback only)
# ---------------------------------------------------------------------------
# Pronouns that always map to the user's primary node
PRONOUN_TO_USER = {"我", "用户", "用户本人", "本人"}
# Primary user name (can be fetched from config or graph)
PRIMARY_USER = "赵禹"

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

_CREATIVE_RECOMBINATION_SYSTEM = """\
You are a creative thinking engine. Below are several memory fragments from a user's knowledge graph.

Try to discover valuable potential connections or insights between these fragments.

Rules:
- Only return truly valuable, actionable insights
- Do NOT force connections between unrelated things
- Insights should be practically helpful (side business opportunities, learning directions, problem solutions, etc.)
- If there is no meaningful connection, return {"insight": null}

Return ONLY valid JSON:
{
  "insight": "one-sentence insight description" | null,
  "reasoning": "why these fragments are connected",
  "actionable": "how the user can leverage this insight",
  "source_nodes": ["node_name1", "node_name2"]
}
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

                        # Handle interference: invalidate old relations if needed
                        relations_to_invalidate = entity.get("relations_to_invalidate", [])
                        if relations_to_invalidate:
                            await self._invalidate_relations(
                                node_id, relations_to_invalidate, tenant_id, user_id
                            )

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

        # Step 5.4: Resolve conflicts from interference detection
        try:
            conflicts_resolved = await self._resolve_conflicts(tenant_id, user_id)
            stats["conflicts_resolved"] = conflicts_resolved
        except Exception as e:
            logger.warning("Conflict resolution failed: %s", e)

        # Step 5.5: Repair orphan nodes (suggest missing relations)
        try:
            orphan_rels = await self._repair_orphans(tenant_id, user_id, name_to_id)
            stats["relations_created"] += orphan_rels
        except Exception as e:
            logger.warning("Orphan repair failed: %s", e)

        # Step 5.6: Creative recombination (after pattern discovery)
        try:
            insights_created = await self._creative_recombination(tenant_id, user_id)
            stats["insights_created"] = insights_created
        except Exception as e:
            logger.warning("Creative recombination failed: %s", e)

        # Step 5.7: Graph hygiene / cleaning (after all writes complete)
        try:
            review_stats = await self._llm_graph_review(tenant_id, user_id)
            stats["llm_review_merged"] = review_stats.get("merged", 0)
            stats["llm_review_demoted"] = review_stats.get("demoted", 0)
            stats["llm_review_dormant"] = review_stats.get("dormant", 0)
        except Exception as e:
            logger.warning("LLM graph review failed: %s", e)

        try:
            orphans_handled = await self._handle_orphan_nodes(tenant_id, user_id)
            stats["orphans_handled"] = orphans_handled
        except Exception as e:
            logger.warning("Orphan node handling failed: %s", e)

        try:
            await self.graph.apply_decay(tenant_id, user_id)
        except Exception as e:
            logger.error("apply_decay failed: %s", e)

        # Step 6: Check spaced repetition (mark important memories for review)
        try:
            review_count = await self._check_spaced_repetition(tenant_id, user_id)
            stats["memories_marked_for_review"] = review_count
        except Exception as e:
            logger.warning("Spaced repetition check failed: %s", e)

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

    # ------------------------------------------------------------------
    # Interference handling
    # ------------------------------------------------------------------

    async def _invalidate_relations(
        self,
        node_id: str,
        relation_types: List[str],
        tenant_id: str,
        user_id: str,
    ) -> None:
        """
        标记指定类型的关系为无效（设置valid_until为当前时间）。

        Args:
            node_id: 节点ID
            relation_types: 要失效的关系类型列表
            tenant_id: 租户ID
            user_id: 用户ID
        """
        try:
            relations = await self.graph.get_relations(node_id)
            now = datetime.utcnow()

            for rel in relations:
                # Check if this relation type should be invalidated
                if rel.type in relation_types and rel.from_id == node_id:
                    # Only invalidate outgoing relations (from this node)
                    await self.graph.update_relation(
                        rel.from_id, rel.to_id, rel.type,
                        {"valid_until": now.isoformat()}
                    )
                    log_event("consolidation_interference",
                             f"Invalidated relation {rel.type} from {node_id[:8]}",
                             {"from": rel.from_id, "to": rel.to_id, "type": rel.type})
                    logger.info("Invalidated relation %s: %s -> %s (interference)",
                               rel.type, rel.from_id[:8], rel.to_id[:8])
        except Exception as e:
            logger.warning("Failed to invalidate relations for %s: %s", node_id, e)

    async def _resolve_conflicts(self, tenant_id: str, user_id: str) -> int:
        """
        扫描并解决所有带冲突标记的节点。

        Args:
            tenant_id: 租户ID
            user_id: 用户ID

        Returns:
            解决的冲突数量
        """
        try:
            # Find all nodes with conflict markers
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            conflict_nodes = [
                n for n in all_nodes
                if n.properties.get("_conflict_with")
            ]

            if not conflict_nodes:
                return 0

            resolved_count = 0
            for node in conflict_nodes:
                try:
                    conflict_with = node.properties.get("_conflict_with")
                    old_summary = node.properties.get("_conflict_old_summary", "")
                    new_summary = node.properties.get("_conflict_new_summary", "")

                    # Use LLM to decide how to resolve
                    system_prompt = """\
You are a conflict resolver for a memory system. Two pieces of information contradict each other.

Decide how to resolve:
1. "keep_new" - New information is correct, discard old
2. "keep_old" - Old information is correct, discard new
3. "keep_both" - Both are valid at different times, keep timeline
4. "merge" - Merge both into a coherent statement

Return ONLY valid JSON:
{
  "resolution": "keep_new" | "keep_old" | "keep_both" | "merge",
  "reason": "brief explanation",
  "merged_summary": "merged text if resolution=merge"
}
"""
                    user_prompt = f"""Entity: {node.name}

Old information: {old_summary}

New information: {new_summary}

How should we resolve this conflict?"""

                    result = await call_llm_json(system_prompt, user_prompt, temperature=0.1)
                    resolution = result.get("resolution", "keep_both")

                    # Apply resolution
                    updates = {}
                    if resolution == "keep_new":
                        # Keep new summary, clear conflict markers
                        updates["summary"] = new_summary
                    elif resolution == "keep_old":
                        # Revert to old summary
                        updates["summary"] = old_summary
                    elif resolution == "keep_both":
                        # Add timeline annotation
                        updates["summary"] = f"{old_summary} [后更新为: {new_summary}]"
                    elif resolution == "merge":
                        # Use LLM-merged version
                        updates["summary"] = result.get("merged_summary", new_summary)

                    # Clear conflict markers
                    new_props = {k: v for k, v in node.properties.items()
                                if not k.startswith("_conflict_")}
                    updates["properties"] = new_props

                    await self.graph.update_node(node.id, updates)
                    resolved_count += 1

                    log_event("consolidation_conflict_resolved",
                             f"Resolved conflict for {node.name}: {resolution}",
                             {"node_id": node.id, "resolution": resolution})
                    logger.info("Resolved conflict for %s: %s (%s)",
                               node.name, resolution, result.get("reason"))

                except Exception as e:
                    logger.warning("Failed to resolve conflict for node %s: %s", node.id, e)

            return resolved_count

        except Exception as e:
            logger.error("Conflict resolution scan failed: %s", e)
            return 0

    # ------------------------------------------------------------------
    # Spaced repetition
    # ------------------------------------------------------------------

    async def _check_spaced_repetition(self, tenant_id: str, user_id: str) -> int:
        """
        扫描图谱中所有active节点，找出重要但快被遗忘的记忆，标记为需要复习。

        间隔重复算法：
        - 第1次复习：1天后
        - 第2次复习：3天后
        - 第3次复习：7天后
        - 第4次复习：21天后
        - 之后每次间隔翻倍

        Args:
            tenant_id: 租户ID
            user_id: 用户ID

        Returns:
            标记为需要复习的节点数量
        """
        try:
            # Find all active nodes with importance >= 6
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id, min_strength=0.0)
            important_nodes = [n for n in all_nodes if n.importance >= 6.0]

            if not important_nodes:
                return 0

            now = datetime.utcnow()
            marked_count = 0

            # Spaced repetition intervals (in days)
            INTERVALS = [1, 3, 7, 21]  # First 4 reviews

            for node in important_nodes:
                props = node.properties or {}

                # Skip if already marked for review
                if props.get("needs_review"):
                    continue

                # Get review history
                review_count = props.get("review_count", 0)
                last_review_date_str = props.get("last_review_date")
                next_review_date_str = props.get("next_review_date")

                # Calculate next review date based on review count
                if review_count < len(INTERVALS):
                    interval_days = INTERVALS[review_count]
                else:
                    # After 4th review, double the interval each time
                    interval_days = INTERVALS[-1] * (2 ** (review_count - len(INTERVALS) + 1))

                # Determine if review is needed
                needs_review = False

                if not last_review_date_str:
                    # Never reviewed, use last_accessed as baseline
                    last_accessed = node.last_accessed
                    if isinstance(last_accessed, datetime):
                        last_accessed_dt = last_accessed
                    elif isinstance(last_accessed, str):
                        try:
                            last_accessed_dt = datetime.fromisoformat(last_accessed.replace("Z", "+00:00"))
                            last_accessed_dt = last_accessed_dt.replace(tzinfo=None)
                        except Exception:
                            last_accessed_dt = now
                    else:
                        last_accessed_dt = now

                    days_since_access = (now - last_accessed_dt).days
                    # If retrieval_strength is dropping and it's been a while, mark for review
                    if node.retrieval_strength < 3.0 and days_since_access >= interval_days:
                        needs_review = True
                        next_review_date = now
                else:
                    # Has review history, check if next review date has passed
                    if next_review_date_str:
                        try:
                            next_review_dt = datetime.fromisoformat(next_review_date_str.replace("Z", "+00:00"))
                            next_review_dt = next_review_dt.replace(tzinfo=None)
                            if now >= next_review_dt:
                                needs_review = True
                                next_review_date = now
                        except Exception:
                            pass

                if needs_review:
                    # Mark node for review
                    updates = {
                        "properties": {
                            **props,
                            "needs_review": True,
                            "next_review_date": next_review_date.isoformat(),
                        }
                    }
                    await self.graph.update_node(node.id, updates)
                    marked_count += 1
                    logger.info(
                        "Marked node %s (entity=%s, importance=%.1f, strength=%.1f) for spaced repetition review",
                        node.id[:8], node.name, node.importance, node.retrieval_strength
                    )

            if marked_count > 0:
                logger.info("Spaced repetition: marked %d memories for review", marked_count)

            return marked_count

        except Exception as e:
            logger.error("Spaced repetition check failed: %s", e)
            return 0

    # ------------------------------------------------------------------
    # Creative recombination
    # ------------------------------------------------------------------

    async def _creative_recombination(self, tenant_id: str, user_id: str) -> int:
        """
        创造性重组：随机组合不同记忆片段，尝试发现有价值的洞察。

        Returns:
            创建的洞察节点数量
        """
        try:
            # 1. 获取所有active节点，按zone分组
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            if len(all_nodes) < 5:
                # 节点太少，无法进行有意义的重组
                return 0

            episodic_nodes = [n for n in all_nodes if n.zone == "episodic"]
            semantic_nodes = [n for n in all_nodes if n.zone == "semantic"]
            other_nodes = [n for n in all_nodes if n.zone not in ("episodic", "semantic")]

            # 每次巩固最多尝试2次创造性重组
            insights_created = 0
            for attempt in range(2):
                # 2. 随机抽取5-8个节点（确保多样性）
                sample_size = random.randint(5, 8)
                selected_nodes = []

                # 至少1个episodic
                if episodic_nodes:
                    selected_nodes.extend(random.sample(episodic_nodes, min(1, len(episodic_nodes))))

                # 至少1个semantic
                if semantic_nodes:
                    selected_nodes.extend(random.sample(semantic_nodes, min(1, len(semantic_nodes))))

                # 填充剩余名额（从所有节点中随机选择）
                remaining = sample_size - len(selected_nodes)
                if remaining > 0:
                    available = [n for n in all_nodes if n not in selected_nodes]
                    if available:
                        selected_nodes.extend(random.sample(available, min(remaining, len(available))))

                if len(selected_nodes) < 3:
                    # 样本太少，跳过这次尝试
                    continue

                # 3. 构建prompt
                fragments = "\n".join(
                    f"- [{n.zone}] {n.name}: {n.summary or '(no summary)'}  (tags: {', '.join(n.tags[:3])})"
                    for n in selected_nodes
                )
                user_prompt = f"Memory fragments:\n\n{fragments}"

                # 4. 调用LLM尝试发现洞察
                try:
                    result = await call_llm_json(
                        _CREATIVE_RECOMBINATION_SYSTEM,
                        user_prompt,
                        temperature=0.7  # 较高温度鼓励创造性
                    )
                except Exception as e:
                    logger.warning("Creative recombination LLM call failed (attempt %d): %s", attempt + 1, e)
                    continue

                insight_text = result.get("insight")
                if not insight_text or insight_text == "null":
                    # 没有发现有意义的洞察，这是正常的
                    logger.debug("Creative recombination attempt %d: no insight found", attempt + 1)
                    continue

                # 5. 创建洞察节点
                reasoning = result.get("reasoning", "")
                actionable = result.get("actionable", "")
                source_node_names = result.get("source_nodes", [])

                # 构建洞察节点的summary
                insight_summary = f"{insight_text} | 原因: {reasoning} | 行动: {actionable}"

                try:
                    insight_node = Node(
                        name=f"洞察: {insight_text[:50]}",  # 限制名称长度
                        tags=["洞察", "创造性重组"],
                        summary=insight_summary,
                        zone="semantic",
                        importance=6.0,  # 中等重要，等用户确认后提升
                        confidence=0.5,  # 未经验证的洞察
                        properties={
                            "insight_type": "creative_recombination",
                            "reasoning": reasoning,
                            "actionable": actionable,
                            "source_count": len(selected_nodes),
                        }
                    )
                    created_insight = await self.graph.create_node(insight_node, tenant_id, user_id)

                    # 6. 创建关系：洞察节点 -[DERIVED_FROM]-> 源节点
                    for source_node in selected_nodes:
                        try:
                            relation = Relation(
                                from_id=created_insight.id,
                                to_id=source_node.id,
                                type="DERIVED_FROM",
                                description="创造性重组发现的洞察",
                                valid_from=datetime.utcnow(),
                                source_session="consolidator-creative-recombination",
                            )
                            await self.graph.create_relation(relation)
                        except Exception as e:
                            logger.warning("Failed to create DERIVED_FROM relation: %s", e)

                    insights_created += 1
                    log_event("consolidation_creative_insight",
                             f"Created insight: {insight_text[:80]}",
                             {
                                 "insight_id": created_insight.id,
                                 "source_count": len(selected_nodes),
                                 "reasoning": reasoning[:100],
                             })
                    logger.info("Creative recombination: created insight '%s' from %d nodes",
                               insight_text[:80], len(selected_nodes))

                except Exception as e:
                    logger.warning("Failed to create insight node: %s", e)
                    continue

            return insights_created

        except Exception as e:
            logger.error("Creative recombination failed: %s", e)
            return 0

    # ------------------------------------------------------------------
    # Graph hygiene / cleaning
    # ------------------------------------------------------------------

    async def _llm_graph_review(self, tenant_id: str, user_id: str) -> Dict[str, int]:
        """
        LLM-driven global graph review and hygiene.

        Fetches all active nodes, sends them to LLM in batches for review.
        LLM decides for each node:
        - keep: No action needed
        - merge: Merge into another node (duplicate)
        - demote: Lower importance (low-value content)
        - dormant: Mark as dormant (outdated/worthless)

        Returns:
            Stats dict with counts of actions taken
        """
        stats = {"merged": 0, "demoted": 0, "dormant": 0}

        try:
            # Fetch all active nodes
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            if not all_nodes:
                logger.info("No active nodes to review")
                return stats

            logger.info("LLM graph review: reviewing %d nodes", len(all_nodes))

            # Process in batches (max 30 nodes per batch, max 3 batches = 90 nodes)
            batch_size = 30
            max_batches = 3
            batches = [all_nodes[i:i + batch_size] for i in range(0, len(all_nodes), batch_size)]
            batches = batches[:max_batches]

            for batch_idx, batch in enumerate(batches):
                logger.info("Processing batch %d/%d (%d nodes)", batch_idx + 1, len(batches), len(batch))

                # Build node summary for LLM
                nodes_json = []
                for node in batch:
                    nodes_json.append({
                        "name": node.name,
                        "tags": node.tags,
                        "summary": node.summary or "",
                        "aliases": node.aliases,
                        "importance": node.importance,
                    })

                system_prompt = """\
You are a knowledge graph maintenance expert. Review the following nodes from a personal knowledge graph.

Return ONLY valid JSON array:
[
  {
    "name": "node name",
    "action": "keep|merge|demote|dormant",
    "merge_into": "target node name (for merge) or null",
    "reason": "brief reason"
  }
]

Actions:
1. "keep" — Valuable, keep as-is
2. "merge" — Duplicate of another node, should merge
   - Specify merge_into (target node name)
3. "demote" — Low value, reduce importance
   - Reasons: trivial details, over-abstraction, debug residue, universal concepts
4. "dormant" — Outdated or worthless, should be dormant

Principles:
- People, organizations, projects, plans → usually keep
- Same person/thing with different names → merge (e.g., "赵禹" and "禹哥")
- Pronoun nodes ("我", "用户", "本人") → merge to user's primary node
- Pure numbers, specific food items → demote
- Debug/technical details from testing → demote or dormant
- When uncertain → keep (prefer to preserve)
"""

                user_prompt = f"""\
Node list:
{json.dumps(nodes_json, ensure_ascii=False, indent=2)}
"""

                # Call LLM
                try:
                    result = await call_llm_json(system_prompt, user_prompt, temperature=0.2)
                    actions = result if isinstance(result, list) else result.get("actions", [])
                except Exception as e:
                    logger.error("LLM graph review batch %d failed: %s. Skipping batch.", batch_idx + 1, e)
                    continue

                # Execute actions
                action_map = {a.get("name", ""): a for a in actions}
                for node in batch:
                    action_data = action_map.get(node.name)
                    if not action_data:
                        continue

                    action = action_data.get("action", "keep")
                    reason = action_data.get("reason", "")

                    if action == "keep":
                        continue

                    elif action == "merge":
                        merge_into = action_data.get("merge_into")
                        if not merge_into:
                            logger.warning("Merge action for '%s' missing target, skipping", node.name)
                            continue

                        # Find target node
                        target_nodes = await self.graph.find_nodes_by_name(merge_into, tenant_id, user_id)
                        if not target_nodes:
                            logger.warning("Merge target '%s' not found for '%s', skipping", merge_into, node.name)
                            continue

                        target_node = target_nodes[0]
                        if target_node.id == node.id:
                            logger.warning("Cannot merge node '%s' into itself, skipping", node.name)
                            continue

                        try:
                            await self.graph.merge_nodes(target_node.id, node.id)
                            stats["merged"] += 1
                            log_event("llm_graph_review_merge",
                                     f"Merged '{node.name}' into '{merge_into}': {reason}",
                                     {"source": node.name, "target": merge_into, "reason": reason})
                            logger.info("Merged '%s' into '%s': %s", node.name, merge_into, reason)
                        except Exception as e:
                            logger.warning("Failed to merge '%s' into '%s': %s", node.name, merge_into, e)

                    elif action == "demote":
                        try:
                            # Reduce importance by 0.3
                            new_importance = max(0.0, node.importance - 0.3)
                            await self.graph.update_node(node.id, {"importance": new_importance})
                            stats["demoted"] += 1
                            log_event("llm_graph_review_demote",
                                     f"Demoted '{node.name}': {reason}",
                                     {"node": node.name, "reason": reason})
                            logger.info("Demoted '%s': %s", node.name, reason)
                        except Exception as e:
                            logger.warning("Failed to demote '%s': %s", node.name, e)

                    elif action == "dormant":
                        try:
                            await self.graph.update_node(node.id, {"status": "dormant"})
                            stats["dormant"] += 1
                            log_event("llm_graph_review_dormant",
                                     f"Marked '{node.name}' as dormant: {reason}",
                                     {"node": node.name, "reason": reason})
                            logger.info("Marked '%s' as dormant: %s", node.name, reason)
                        except Exception as e:
                            logger.warning("Failed to mark '%s' as dormant: %s", node.name, e)

            logger.info("LLM graph review complete: %s", stats)
            return stats

        except Exception as e:
            logger.error("LLM graph review failed: %s", e)
            return stats

    async def _handle_orphan_nodes(self, tenant_id: str, user_id: str) -> int:
        """
        Handle orphan nodes (nodes with no relationships).
        - Reminder nodes: connect to user
        - Low importance + old: mark as dormant
        - Others: keep (may be newly created)

        Returns:
            Number of nodes processed
        """
        try:
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)

            orphans = []
            for node in all_nodes:
                rels = await self.graph.get_relations(node.id)
                if not rels:
                    orphans.append(node)

            if not orphans:
                return 0

            processed_count = 0
            now = datetime.utcnow()

            # Find primary user node for connecting reminders
            primary_nodes = await self.graph.find_nodes_by_name(PRIMARY_USER, tenant_id, user_id)
            primary_user_id = primary_nodes[0].id if primary_nodes else None

            for node in orphans:
                # Check if it's a reminder
                if "提醒" in node.tags and primary_user_id:
                    try:
                        relation = Relation(
                            from_id=primary_user_id,
                            to_id=node.id,
                            type="HAS_REMINDER",
                            description="系统自动连接的提醒",
                            valid_from=now,
                            source_session="consolidator-orphan-handler",
                        )
                        await self.graph.create_relation(relation)
                        processed_count += 1
                        logger.info("Connected orphan reminder '%s' to user", node.name)
                    except Exception as e:
                        logger.warning("Failed to connect reminder: %s", e)
                    continue

                # Check if it's low importance and old
                if node.importance < 3.0:
                    created_at = node.created_at
                    if isinstance(created_at, str):
                        try:
                            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            created_at = created_at.replace(tzinfo=None)
                        except Exception:
                            created_at = now
                    elif not isinstance(created_at, datetime):
                        created_at = now

                    days_old = (now - created_at).days
                    if days_old > 7:
                        try:
                            await self.graph.update_node(node.id, {"status": "dormant"})
                            processed_count += 1
                            logger.info("Marked old low-importance orphan '%s' as dormant", node.name)
                        except Exception as e:
                            logger.warning("Failed to mark orphan as dormant: %s", e)

            if processed_count > 0:
                logger.info("Orphan handler: processed %d orphan nodes", processed_count)

            return processed_count

        except Exception as e:
            logger.error("Orphan node handling failed: %s", e)
            return 0
