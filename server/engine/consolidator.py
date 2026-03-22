"""
Consolidator engine component for the brain-memory service.
Corresponds to the sleep consolidation mechanism in the human brain.

巩固器引擎组件 — 对应人脑的睡眠巩固机制。
将缓冲区中的记忆单元转移到长期Neo4j图谱中。

v2: 适配encoder v2（action/aliases_to_add/tag合并）+ 逐单元归档。
v3: 新增隐含关系推导模块，提示词中文化。

优化历史：
- 2026-03-17: 提示词中文化，新增隐含关系推导（_infer_implicit_relations）
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta
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
你是记忆系统的模式发现引擎。分析提供的记忆片段，识别跨事件模式、反复出现的主题或新兴趋势。

返回格式（仅JSON）：
{
  "patterns": ["模式描述1", "模式描述2"],
  "conflicts": ["冲突描述"]
}
"""

# ---------------------------------------------------------------------------
# 孤儿节点关系修复提示词
# ---------------------------------------------------------------------------
_ORPHAN_RELATION_SYSTEM = """\
你是知识图谱关系构建器。给定孤儿节点（无关系）和已连接节点，建议关系。

规则：
- 只建议明确隐含的关系。不要猜测。
- 关系类型：UPPER_SNAKE_CASE（如WEIGHS、INTERESTED_IN、PART_OF）或中文。
- 每个孤儿最多1个关系。描述保持简短（10字以内）。
- 如果某个孤儿没有明确的关系，跳过它。

返回格式（仅JSON）：
{"suggested_relations": [{"from_name": "A", "to_name": "B", "type": "关系类型", "description": "简短描述"}]}
"""

# ---------------------------------------------------------------------------
# 创造性重组提示词
# ---------------------------------------------------------------------------
_CREATIVE_RECOMBINATION_SYSTEM = """\
你是创造性思维引擎。以下是用户知识图谱中的若干记忆片段。

尝试发现这些片段之间有价值的潜在联系或洞察。

规则：
- 只返回真正有价值、可操作的洞察
- 不要强行关联不相关的事物
- 洞察应具有实际帮助（副业机会、学习方向、问题解决方案等）
- 如果没有有意义的联系，返回 {"insight": null}

返回格式（仅JSON）：
{
  "insight": "一句话洞察描述" | null,
  "reasoning": "为什么这些片段有联系",
  "actionable": "用户如何利用这个洞察",
  "source_nodes": ["节点名1", "节点名2"]
}
"""

# ---------------------------------------------------------------------------
# 隐含关系推导提示词（v3新增）
# ---------------------------------------------------------------------------
_INFER_RELATIONS_SYSTEM = """\
你是知识图谱关系推导引擎。给定一组节点及其已有关系，推导缺失的隐含关系。

推导规则：
- 传递性关系：如果A和B都与C有相同类型的关系，推导A和B之间可能的关系
- 层级关系：如果A是C的上级，B是C的下级，推导A和B的层级关系
- 组织关系：如果A和B属于同一组织/团队/项目，推导他们之间的协作关系
- 因果关系：如果A导致B，B导致C，推导A和C的间接因果关系
- 只推导高置信度（>90%）的关系
- 不要推导已经明确存在的关系
- 不要跨不相关领域推导关系

返回格式（仅JSON）：
{
  "inferred_relations": [
    {
      "from_name": "节点名1",
      "to_name": "节点名2",
      "type": "关系类型",
      "description": "关系描述",
      "confidence": 0.95,
      "reasoning": "推导理由"
    }
  ]
}
"""


class Consolidator:
    """Memory consolidator — sleep consolidation mechanism."""

    def __init__(self, graph: GraphStore, tag_dict: TagDict, buffer: EncoderBuffer) -> None:
        self.graph = graph
        self.tag_dict = tag_dict
        self.buffer = buffer

    async def consolidate(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """
        执行睡眠巩固：将 Buffer 中的记忆单元转移到长期图谱。

        流程：
        1. 读取未归档的记忆单元
        2. 过滤低重要性单元（importance < 3.0）
        3. 逐单元处理：创建/更新节点和关系
        4. 归档已处理的单元
        5. 模式发现和冲突解决
        6. 孤儿节点修复
        7. 创意重组
        8. 图谱清理

        Args:
            tenant_id: 租户ID
            user_id: 用户ID

        Returns:
            统计信息字典
        """
        stats: Dict[str, Any] = {
            "nodes_created": 0, "nodes_updated": 0, "nodes_merged": 0,
            "relations_created": 0, "patterns_discovered": [], "conflicts_found": [],
            "units_processed": 0, "units_skipped": 0,
        }

        # 步骤1: 读取未归档的记忆单元
        units = self.buffer.read_unarchived(tenant_id, user_id)
        if not units:
            logger.info("No unarchived units for tenant=%s user=%s", tenant_id, user_id)
            return stats

        # 步骤2: 过滤低重要性单元（importance < 3.0）
        valid_units = [u for u in units if float(u.get("importance", 0)) >= 3.0]
        low_imp_units = [u for u in units if float(u.get("importance", 0)) < 3.0]
        stats["units_skipped"] = len(low_imp_units)

        log_event("consolidation_start",
            f"Processing {len(valid_units)} units (skipped {stats['units_skipped']} low-imp)",
            {"tenant": tenant_id, "total": len(units), "valid": len(valid_units)})

        name_to_id: Dict[str, str] = {}

        # 步骤3: 处理有效单元（创建/更新节点和关系）
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

        # 步骤4: 归档低重要性单元（不处理，直接归档）
        for unit in low_imp_units:
            uid = unit.get("id", "")
            if uid:
                self.buffer.archive_by_id(uid)

        # 步骤5: 模式发现和冲突检测
        patterns, conflicts = await self._discover_patterns(valid_units, tenant_id, user_id)
        stats["patterns_discovered"] = patterns
        stats["conflicts_found"] = conflicts

        # 步骤6: 解决干扰检测发现的冲突
        try:
            conflicts_resolved = await self._resolve_conflicts(tenant_id, user_id)
            stats["conflicts_resolved"] = conflicts_resolved
        except Exception as e:
            logger.warning("Conflict resolution failed: %s", e)

        # 步骤7: 修复孤儿节点（建议缺失的关系）
        try:
            orphan_rels = await self._repair_orphans(tenant_id, user_id, name_to_id)
            stats["relations_created"] += orphan_rels
        except Exception as e:
            logger.warning("Orphan repair failed: %s", e)

        # 步骤8: 创意重组（模式发现后的洞察生成）
        try:
            insights_created = await self._creative_recombination(tenant_id, user_id)
            stats["insights_created"] = insights_created
        except Exception as e:
            logger.warning("Creative recombination failed: %s", e)

        # 步骤9: 图谱清理（所有写入完成后）
        try:
            review_stats = await self._llm_graph_review(tenant_id, user_id)
            stats["llm_review_merged"] = review_stats.get("merged", 0)
            stats["llm_review_demoted"] = review_stats.get("demoted", 0)
            stats["llm_review_dormant"] = review_stats.get("dormant", 0)
        except Exception as e:
            logger.warning("LLM graph review failed: %s", e)

        # 步骤10: 隐含关系推导（在图谱清理后，确保重复节点已合并）
        try:
            inferred_rels = await self._infer_implicit_relations(tenant_id, user_id)
            stats["inferred_relations"] = inferred_rels
            stats["relations_created"] += inferred_rels
        except Exception as e:
            logger.warning("Implicit relation inference failed: %s", e)

        # 步骤11: 应用遗忘衰减（降低长期未访问节点的检索强度）
        try:
            await self.graph.apply_decay(tenant_id, user_id)
        except Exception as e:
            logger.error("apply_decay failed: %s", e)

        # 步骤12: 间隔重复检查（标记重要记忆以供复习）
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
        """
        根据 encoder v2 的 action 字段插入或更新实体。
        创建/更新后自动生成 embedding。

        Args:
            entity: 实体数据（包含 action, name, existing_id 等）
            tenant_id: 租户ID
            user_id: 用户ID
            unit: 原始记忆单元（用于日志）

        Returns:
            (node_id, created, merged) 元组
            - node_id: 节点ID
            - created: 是否新建
            - merged: 是否合并
        """
        name = entity.get("name", "").strip()
        if not name:
            return None, False, False

        action = entity.get("action", "create")
        existing_id = entity.get("existing_id")
        aliases = entity.get("aliases_to_add", [])
        tags = entity.get("tags", [])

        # 情况1: 合并或更新现有节点
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

                # 为更新后的节点生成embedding
                await self._ensure_node_embedding(existing_id, name, summary or "")

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
                # 为已有节点补充embedding
                await self._ensure_node_embedding(eid, name, summary or "")
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

            # 为新建节点生成embedding
            await self._ensure_node_embedding(
                created_node.id, name, entity.get("summary", ""))

            log_event("consolidation_entity", f"create: {name}", {
                "action": "create", "node_id": created_node.id[:8], "tags": tags[:3]})
            return created_node.id, True, False
        except Exception as e:
            logger.error("create_node failed for '%s': %s", name, e)
            return None, False, False

    # ------------------------------------------------------------------
    # 节点Embedding生成（确保图谱节点都有向量表示）
    # ------------------------------------------------------------------

    async def _ensure_node_embedding(self, node_id: str, name: str, summary: str) -> None:
        """
        为图谱节点生成embedding。
        
        使用 name + summary 拼接作为embedding文本，
        调用embedding API生成向量后写入Neo4j节点。
        如果节点已有embedding则跳过。
        
        Args:
            node_id: 节点ID
            name: 节点名称
            summary: 节点摘要
        """
        try:
            # 直接查Neo4j检查是否已有embedding
            driver = self.graph._ensure_connected()
            async with driver.session() as session:
                result = await session.run(
                    "MATCH (n:MemoryNode {id: $nid}) RETURN n.embedding IS NOT NULL as has_emb",
                    nid=node_id
                )
                record = await result.single()
                if record and record["has_emb"]:
                    return  # 已有embedding，跳过
            
            # 拼接embedding文本：name + summary
            emb_text = f"{name}: {summary}" if summary else name
            
            from server.engine.embedding_client import get_embedding
            embedding = await get_embedding(emb_text, type_="db")
            
            if embedding and any(v != 0.0 for v in embedding[:10]):
                await self.graph.update_node_embedding(node_id, embedding)
                logger.debug("Generated embedding for node '%s'", name)
            else:
                logger.warning("Empty embedding for node '%s'", name)
        except Exception as e:
            logger.warning("Failed to generate embedding for node '%s': %s", name, e)

    # ------------------------------------------------------------------
    # Relation upsert
    # ------------------------------------------------------------------

    async def _upsert_relation(
        self, rel_data: Dict[str, Any], name_to_id: Dict[str, str],
        tenant_id: str, user_id: str, unit: Dict[str, Any],
    ) -> bool:
        """
        创建关系（如果不存在）。

        Args:
            rel_data: 关系数据（from_name, to_name, type, description等）
            name_to_id: 实体名到节点ID的映射
            tenant_id: 租户ID（未使用，保留用于扩展）
            user_id: 用户ID（未使用，保留用于扩展）
            unit: 原始记忆单元

        Returns:
            是否成功创建关系
        """
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
        self, units: List[Dict[str, Any]], tenant_id: str, user_id: str
    ) -> Tuple[List[str], List[str]]:
        """
        使用LLM发现跨事件模式，并将模式持久化到图谱。

        Args:
            units: 记忆单元列表
            tenant_id: 租户ID
            user_id: 用户ID

        Returns:
            (patterns, conflicts) 元组
        """
        if len(units) < 3:
            return [], []
        fragments = "\n".join(
            f"- [{u.get('timestamp', '')[:10]}] {u.get('message', '')[:200]}"
            for u in units[-30:]
        )
        try:
            result = await call_llm_json(_PATTERN_SYSTEM, f"Memory fragments:\n{fragments}")
            patterns = result.get("patterns", [])
            conflicts = result.get("conflicts", [])

            # 将发现的模式持久化到图谱
            for pattern in patterns:
                try:
                    pattern_node = Node(
                        name=f"模式: {pattern[:50]}",
                        tags=["模式", "自动发现"],
                        summary=pattern,
                        zone="semantic",
                        importance=5.0,
                        confidence=0.6,
                        properties={"pattern_type": "cross_event", "discovered_at": datetime.utcnow().isoformat()}
                    )
                    await self.graph.create_node(pattern_node, tenant_id, user_id)
                except Exception as e:
                    logger.warning("Failed to persist pattern: %s", e)

            return patterns, conflicts
        except Exception as e:
            logger.warning("Pattern discovery failed: %s", e)
            return [], []

    async def _repair_orphans(
        self, tenant_id: str, user_id: str, name_to_id: Dict[str, str]
    ) -> int:
        """
        查找孤儿节点并通过LLM建议缺失的关系。

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            name_to_id: 实体名称到ID的映射

        Returns:
            创建的关系数量
        """
        all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)

        # 分类节点：孤儿节点（无关系）vs 已连接节点
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

        # 构建LLM输入
        orphan_text = "\n".join(f"- {o['name']} (tags={o['tags']}, summary={o['summary'][:60]})" for o in orphans)
        connected_text = "\n".join(f"- {c['name']} (tags={c['tags']}, summary={c['summary'][:60]})" for c in connected[:20])

        user_prompt = f"孤儿节点（无关系）:\n{orphan_text}\n\n已连接节点:\n{connected_text}"

        try:
            result = await call_llm_json(_ORPHAN_RELATION_SYSTEM, user_prompt, temperature=0.1)
        except Exception as e:
            logger.warning("Orphan relation suggestion failed: %s", e)
            return 0

        # 构建name→id映射（包含所有节点）
        all_name_to_id = {n.name: n.id for n in all_nodes}
        all_name_to_id.update(name_to_id)
        
        # 创建建议的关系
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
            # 查找所有带冲突标记的节点
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            conflict_nodes = [
                n for n in all_nodes
                if n.properties.get("_conflict_old_summary")
            ]

            if not conflict_nodes:
                return 0

            resolved_count = 0
            for node in conflict_nodes:
                try:
                    old_summary = node.properties.get("_conflict_old_summary", "")
                    new_summary = node.properties.get("_conflict_new_summary", "")

                    # 使用LLM决定如何解决冲突
                    system_prompt = """\
你是记忆系统的冲突解决专家。两条信息相互矛盾。

决定如何解决：
1. "keep_new" - 新信息正确，丢弃旧信息
2. "keep_old" - 旧信息正确，丢弃新信息
3. "keep_both" - 两者在不同时间都有效，保留时间线
4. "merge" - 将两者合并为连贯的陈述

仅返回有效JSON：
{
  "resolution": "keep_new" | "keep_old" | "keep_both" | "merge",
  "reason": "简要说明",
  "merged_summary": "如果resolution=merge则提供合并后的文本"
}
"""
                    user_prompt = f"""实体: {node.name}

旧信息: {old_summary}

新信息: {new_summary}

应该如何解决这个冲突？"""

                    result = await call_llm_json(system_prompt, user_prompt, temperature=0.1)
                    resolution = result.get("resolution", "keep_both")

                    # 应用解决方案
                    updates = {}
                    if resolution == "keep_new":
                        # 保留新摘要，清除冲突标记
                        updates["summary"] = new_summary
                    elif resolution == "keep_old":
                        # 恢复旧摘要
                        updates["summary"] = old_summary
                    elif resolution == "keep_both":
                        # 添加时间线注释
                        updates["summary"] = f"{old_summary} [后更新为: {new_summary}]"
                    elif resolution == "merge":
                        # 使用LLM合并后的版本
                        updates["summary"] = result.get("merged_summary", new_summary)

                    # 清除冲突标记
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
        扫描图谱中所有active节点，对重要记忆进行间隔重复强化。

        直接提升retrieval_strength，模拟复习效果，与apply_decay的自然衰减对抗。
        确保重要记忆不会因长期未访问而衰减到dormant。

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
            完成复习的节点数量
        """
        try:
            # 查找所有重要性>=6的活跃节点
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id, min_strength=0.0)
            important_nodes = [n for n in all_nodes if n.importance >= 6.0]

            if not important_nodes:
                return 0

            now = datetime.utcnow()
            reviewed_count = 0

            # 间隔重复时间间隔（天数）
            INTERVALS = [1, 3, 7, 21]  # 前4次复习

            for node in important_nodes:
                props = node.properties or {}

                # 获取复习历史
                review_count = props.get("review_count", 0)
                last_review_date_str = props.get("last_review_date")

                # 根据复习次数计算下次复习间隔
                if review_count < len(INTERVALS):
                    interval_days = INTERVALS[review_count]
                else:
                    # 第4次复习后，每次间隔翻倍
                    interval_days = INTERVALS[-1] * (2 ** (review_count - len(INTERVALS) + 1))

                # 判断是否需要复习
                needs_review = False

                if not last_review_date_str:
                    # 从未复习过，使用last_accessed作为基准
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
                    # 如果检索强度下降且已过一段时间，进行复习
                    if node.retrieval_strength < 3.0 and days_since_access >= interval_days:
                        needs_review = True
                else:
                    # 有复习历史，检查是否到了下次复习时间
                    try:
                        last_review_dt = datetime.fromisoformat(last_review_date_str.replace("Z", "+00:00"))
                        last_review_dt = last_review_dt.replace(tzinfo=None)
                        days_since_review = (now - last_review_dt).days
                        if days_since_review >= interval_days:
                            needs_review = True
                    except Exception:
                        pass

                if needs_review:
                    # 直接强化记忆：提升retrieval_strength
                    new_strength = min(10.0, node.retrieval_strength + 2.0)
                    new_review_count = review_count + 1

                    # 计算下次复习时间
                    if new_review_count < len(INTERVALS):
                        next_interval = INTERVALS[new_review_count]
                    else:
                        next_interval = INTERVALS[-1] * (2 ** (new_review_count - len(INTERVALS) + 1))

                    next_review_date = now + timedelta(days=next_interval)

                    updated_props = {
                        **props,
                        "review_count": new_review_count,
                        "last_review_date": now.isoformat(),
                        "next_review_date": next_review_date.isoformat(),
                    }

                    await self.graph.update_node(node.id, {
                        "retrieval_strength": new_strength,
                        "properties": updated_props
                    })
                    reviewed_count += 1
                    logger.info(
                        "Spaced repetition: reviewed node %s (entity=%s, strength %.1f→%.1f, review_count=%d, next in %d days)",
                        node.id[:8], node.name, node.retrieval_strength, new_strength, new_review_count, next_interval
                    )

            if reviewed_count > 0:
                logger.info("Spaced repetition: reviewed %d important memories", reviewed_count)

            return reviewed_count

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
    # 隐含关系推导（v3新增）
    # ------------------------------------------------------------------

    async def _infer_implicit_relations(self, tenant_id: str, user_id: str) -> int:
        """
        推导图谱中缺失的隐含关系。

        扫描高重要性节点及其已有关系，利用LLM推导缺失的隐含关系。
        例如：如果A和B都与C有关系，推导A和B之间可能的关系。

        Returns:
            新增的关系数量
        """
        relations_created = 0

        try:
            # 获取所有活跃节点
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            if not all_nodes:
                return 0

            # 筛选高重要性节点（importance >= 5.0）且有至少1个关系的节点
            candidate_nodes = []
            for n in all_nodes:
                if n.importance >= 5.0:
                    rels = await self.graph.get_relations(n.id)
                    if rels:
                        candidate_nodes.append(n)
            
            if len(candidate_nodes) < 2:
                logger.info("Not enough candidate nodes for relation inference (%d)", len(candidate_nodes))
                return 0

            logger.info("Inferring implicit relations among %d candidate nodes", len(candidate_nodes))

            # 获取这些节点之间的已有关系
            existing_relations = []
            for node in candidate_nodes:
                try:
                    rels = await self.graph.get_relations(node.id)
                    for rel in rels:
                        existing_relations.append({
                            "from": rel.get("from_name", ""),
                            "to": rel.get("to_name", ""),
                            "type": rel.get("type", ""),
                        })
                except Exception:
                    continue

            # 构建LLM输入
            nodes_info = []
            for n in candidate_nodes:
                nodes_info.append({
                    "name": n.name,
                    "tags": n.tags,
                    "aliases": n.aliases,
                    "summary": n.summary or "",
                })
            
            # 去重已有关系
            seen = set()
            unique_rels = []
            for r in existing_relations:
                key = f"{r['from']}|{r['to']}|{r['type']}"
                if key not in seen:
                    seen.add(key)
                    unique_rels.append(r)
            
            user_prompt = f"""\
节点列表：
{json.dumps(nodes_info, ensure_ascii=False, indent=2)}

已有关系：
{json.dumps(unique_rels, ensure_ascii=False, indent=2)}

请推导上述节点之间缺失的隐含关系。只推导高置信度（>90%）的关系。
"""

            result = await call_llm_json(
                _INFER_RELATIONS_SYSTEM, user_prompt, temperature=0.1
            )

            inferred = result.get("inferred_relations", [])
            if not inferred:
                logger.info("No implicit relations inferred")
                return 0

            # 构建name→id映射
            name_to_id = {}
            for n in candidate_nodes:
                name_to_id[n.name] = n.id
                for alias in (n.aliases or []):
                    name_to_id[alias] = n.id
            
            # 写入推导出的关系
            for rel in inferred:
                confidence = rel.get("confidence", 0)
                if confidence < 0.9:
                    continue  # 只接受高置信度的推导
                
                from_name = rel.get("from_name", "")
                to_name = rel.get("to_name", "")
                rel_type = rel.get("type", "RELATED_TO")
                description = rel.get("description", rel.get("reasoning", ""))
                
                from_id = name_to_id.get(from_name)
                to_id = name_to_id.get(to_name)
                
                if not from_id or not to_id or from_id == to_id:
                    continue
                
                # 检查关系是否已存在（避免重复）
                existing_key = f"{from_name}|{to_name}|{rel_type}"
                if existing_key in seen:
                    continue
                
                try:
                    relation = Relation(
                        from_id=from_id,
                        to_id=to_id,
                        type=rel_type,
                        description=description[:200] if description else "",
                        tenant_id=tenant_id,
                        user_id=user_id,
                    )
                    await self.graph.create_relation(relation)
                    relations_created += 1
                    seen.add(existing_key)
                    logger.info(
                        "Inferred relation: %s --[%s]--> %s (confidence=%.2f)",
                        from_name, rel_type, to_name, confidence
                    )
                except Exception as e:
                    logger.warning("Failed to create inferred relation %s->%s: %s",
                                 from_name, to_name, e)
            
            logger.info("Implicit relation inference complete: %d relations created",
                       relations_created)
            
        except Exception as e:
            logger.error("Implicit relation inference failed: %s", e)
        
        return relations_created

    # ------------------------------------------------------------------
    # Graph hygiene / cleaning
    # ------------------------------------------------------------------

    async def _llm_graph_review(self, tenant_id: str, user_id: str) -> Dict[str, int]:
        """
        LLM驱动的全局图谱审查和清洁。

        获取所有活跃节点，分批发送给LLM审查。
        LLM为每个节点决定：
        - keep: 无需操作
        - merge: 合并到另一个节点（重复）
        - demote: 降低重要性（低价值内容）
        - dormant: 标记为休眠（过时/无价值）

        Returns:
            包含操作计数的统计字典
        """
        stats = {"merged": 0, "demoted": 0, "dormant": 0}

        try:
            # 获取所有活跃节点
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            if not all_nodes:
                logger.info("No active nodes to review")
                return stats

            logger.info("LLM graph review: reviewing %d nodes", len(all_nodes))

            # 分批处理（每批最多30个节点，最多10批=300个节点）
            batch_size = 30
            max_batches = 10
            batches = [all_nodes[i:i + batch_size] for i in range(0, len(all_nodes), batch_size)]
            batches = batches[:max_batches]

            for batch_idx, batch in enumerate(batches):
                logger.info("Processing batch %d/%d (%d nodes)", batch_idx + 1, len(batches), len(batch))

                # 构建节点摘要供LLM审查
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
你是知识图谱维护专家。审查以下个人知识图谱中的节点。

返回格式（仅JSON数组）：
[
  {
    "name": "节点名称",
    "action": "keep|merge|demote|dormant",
    "merge_into": "目标节点名称（merge时）或null",
    "reason": "简要理由"
  }
]

动作说明：
1. "keep" — 有价值，保持原样
2. "merge" — 与另一个节点重复，应合并
   - 指定merge_into（目标节点名称）
   - **名称匹配**：子串关系（如"鹏程"vs"范鹏程"）、昵称关系（如"凡哥"vs"刘凡"）应合并
3. "demote" — 低价值，降低重要性
   - 原因：琐碎细节、过度抽象、调试残留、通用概念
4. "dormant" — 过时或无价值，应标记为休眠

原则：
- 人物、组织、项目、计划 → 通常keep
- 同一人/事物的不同名称 → merge（如"赵禹"和"禹哥"，"鹏程"和"范鹏程"）
- 代词节点（"我"、"用户"、"本人"）→ merge到用户主节点
- 纯数字、具体食物项 → demote
- 测试中的调试/技术细节 → demote或dormant
- 不确定时 → keep（优先保留）
"""

                user_prompt = f"""\
节点列表:
{json.dumps(nodes_json, ensure_ascii=False, indent=2)}
"""

                # 调用LLM
                try:
                    result = await call_llm_json(system_prompt, user_prompt, temperature=0.2)
                    actions = result if isinstance(result, list) else result.get("actions", [])
                except Exception as e:
                    logger.error("LLM graph review batch %d failed: %s. Skipping batch.", batch_idx + 1, e)
                    continue

                # 执行操作
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

                        # 查找目标节点
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
                            # 降低重要性0.3
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
