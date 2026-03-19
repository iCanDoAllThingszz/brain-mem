"""
Encoder engine component for the brain-memory service.
Corresponds to the hippocampus in the human brain.

编码器引擎组件 — 对应人脑的海马体。
将原始消息转换为结构化记忆单元并写入缓冲区。

v2: 实体生命周期管理 — tag归属 + 去重 + 关系构建 合并为单次LLM调用。

优化历史：
- 2026-03-17: 提示词中文化，加强名称变体识别和关系提取规则
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from server.engine.llm_client import call_llm, call_llm_json
from server.engine.log_writer import LogWriter
from server.models.node import Node
from server.storage.buffer import EncoderBuffer
from server.storage.graph import GraphStore
from server.storage.tag_dict import TagDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimal hardcoded rules (fallback only)
# ---------------------------------------------------------------------------
# Pronouns that always map to the user's primary node
PRONOUN_TO_USER = {"我", "用户", "用户本人", "本人"}
# The primary user name will be fetched from graph or config

# ---------------------------------------------------------------------------
# Step 1: 粗提取 — 从消息中提取原始实体和关系
# ---------------------------------------------------------------------------
_EXTRACT_SYSTEM = """\
你是个人记忆系统的信息提取引擎。提取与用户生活相关的实体和关系。

规则：
- 提取命名实体：人物、组织、地点、概念、事件、决策、计划。
- 只提取与用户个人相关的实体。跳过通用常识（如"地球"、"太阳"、"水"），\
  除非用户与之有个人联系。

- **代词解析**：将"我"、"用户"、"本人"等代词替换为用户的真实姓名（如"赵禹"）。\
  绝不创建名为"用户"或"我"的实体 — 总是解析为真实人名。\
  如果用户姓名未知，使用"用户本人"作为占位符。

- **关键用户别名规则**：以下词汇都指同一个人"赵禹"：\
  我、用户、用户本人、本人、禹哥。绝不为这些创建单独实体。总是使用"赵禹"。

- **名称变体识别**：注意常见名称模式：\
  * 全名 vs 昵称："范鹏程" = "鹏程"，"张钧梦阳" = "梦阳" \
  * 称谓+姓名："凡哥"可能是"刘凡"，"小可"可能是昵称 \
  * 提取时优先使用完整姓名，但将昵称标注为潜在别名

- 分配记忆区域：semantic（语义）/ episodic（情景）/ procedural（程序）/ emotional（情感）
- 为每个实体分配1-2个初步标签（优先中文标签）
- 忽略乱码/编码名称（如"Gbusrw Jflvnkmwi"）— 这些是显示伪影
- 关系类型：UPPER_SNAKE_CASE（如WORKS_AT、DECIDED_TO）或中文（如"同事"、"虚线"）
- 如果消息混合了常识和个人信息，只提取个人相关部分

**关系提取要全面**：
- 提取消息中明确提到的关系
- 提取上下文透露的隐含关系（如"我和鹏程都..."暗示他们是同事/朋友）
- 包括组织关系：REPORTS_TO（汇报给）、MANAGES（管理）、COLLABORATES_WITH（协作）
- 包括社交关系：COLLEAGUE（同事）、FRIEND（朋友）、CLASSMATE（同学）、FAMILY（家人）

返回格式（仅JSON）：
{
  "entities": [
    {"name": "实体名称", "tags": ["标签1"], "zone": "semantic", "summary": "一句话描述"}
  ],
  "relations": [
    {"from_name": "A", "to_name": "B", "type": "关系类型", "description": "关系描述"}
  ]
}
"""
# ---------------------------------------------------------------------------
# Step 2+3+4 合并: 实体解析 — tag归属 + 去重 + 关系构建 一次LLM调用
# ---------------------------------------------------------------------------
_RESOLVE_ENTITY_SYSTEM = """\
你是知识图谱实体解析器。给定一个新提取的实体和图谱中具有相似标签的已有实体，决定如何处理。

你必须决定以下三个动作之一：
1. "merge"（合并）— 新实体与已有实体是同一个（同一人/组织/概念）。\
   当新实体只是已有实体的另一次提及或别名时使用。\
   示例："腾讯"和"Tencent"是同一家公司 → merge。

2. "update"（更新）— 新实体为已有实体添加了新信息。\
   当实体已存在但新提及提供了额外细节时使用。\
   示例：已有"赵禹"没有工作信息，新提及说"赵禹在美团工作" → update。

3. "create"（创建）— 新实体是真正的新实体，与所有已有实体不同。\
   只有在确信是不同实体时才使用。

**重要**：对"create"保持保守。如果有任何可能实体已存在，\
优先选择"merge"或"update"。重复实体比合并实体更糟糕。

**名称匹配规则**：
- 如果新实体名称是已有实体名称的子串（如"鹏程" vs "范鹏程"），\
  它们很可能是同一人 → 优先"merge"
- 如果新实体名称是已有名称的昵称或简称（如"小可" vs "可可"），\
  它们很可能是同一人 → 优先"merge"
- 如果新实体名称仅在称谓/敬称上不同（如"凡哥" vs "刘凡"），\
  它们很可能是同一人 → 优先"merge"
- 不确定时，检查上下文：如果它们出现在相似的角色/关系中，优先"merge"

**关系上下文**：决定merge vs create时，考虑：
- 它们是否共享相同的关系？（如都是赵禹的同事）
- 它们是否有相同的角色？（如都是"虚线leader"）
- 如果任一为是，它们很可能是同一实体 → 优先"merge"

标签分配规则：
- 使用提供的标签分类法。选择最匹配的标签。
- 如果没有现有标签合适，提议一个足够通用可复用的新标签\
  （如"医疗"而非"牙科手术"，"交通"而非"地铁3号线"）。
- 每个实体最多1-2个标签。

返回格式（仅JSON）：
{
  "action": "merge" | "update" | "create",
  "resolved_tags": ["标签1", "标签2"],
  "target_entity_name": "要merge/update到的已有实体名称（create时为null）",
  "aliases_to_add": ["别名1"],
  "summary_update": "更新后的摘要文本（无变化时为null）",
  "properties_update": {},
  "new_relations": [
    {"from_name": "A", "to_name": "B", "type": "关系类型", "description": "关系描述"}
  ],
  "reason": "为什么选择这个action的一句话解释"
}
"""

# ---------------------------------------------------------------------------
# 会话摘要提示词
# ---------------------------------------------------------------------------
_SUMMARY_SYSTEM = """\
你是AI Agent记忆系统的会话摘要器。根据本次会话中海马体编码产生的记忆单元（memory units），\
生成结构化的会话摘要。

每个记忆单元包含：
- message: 经过丘脑重写的高密度语义文本
- entities: 已解析的实体列表（含 action: create/merge/update/skip）
- relations: 已解析的关系列表
- importance: 重要性评分
- emotion_type / emotional_intensity: 情感信息

请基于这些已编码的结构化数据（而非原始对话）进行总结。

返回格式（仅JSON）：
{
  "topics": ["话题1", "话题2"],
  "key_entities": ["本次涉及的关键实体名"],
  "key_conclusions": ["结论1"],
  "pending_points": ["未解决1"],
  "emotional_arc": "positive|negative|neutral|mixed",
  "summary_text": "本次会话中的描述内容, 有条理的将重要信息和背景上下文全部表述清楚。"
}
"""


class Encoder:
    """
    Memory encoder — the hippocampus of the memory system.

    v2 flow:
    1. LLM粗提取实体和关系
    2. 对每个实体，查tag字典确定tag归属
    3. 按tag去图谱检索同类实体
    4. LLM一次性判断：create/merge/update + 关系构建
    5. 去重检查 → 写入buffer

    v3 flow:
    - If category = "cognition": use v2 flow (write to graph)
    - If category = "log_*": write to file + update graph index
    """

    def __init__(self, graph: GraphStore, tag_dict: TagDict, buffer: EncoderBuffer) -> None:
        self.graph = graph
        self.tag_dict = tag_dict
        self.buffer = buffer
        self.log_writer = LogWriter(graph)

    async def encode_message(
        self,
        message: str,
        evaluation: Dict[str, Any],
        tenant_id: str,
        user_id: str,
        session_id: str,
        working_memory: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Encode a message into a structured memory unit.

        v3: Routes to cognition encoding or log encoding based on category.
        """
        category = evaluation.get("category", "cognition")

        if category == "cognition":
            # Original flow: extract entities → write to graph buffer
            return await self._encode_cognition(
                message, evaluation, tenant_id, user_id, session_id, working_memory
            )
        elif category == "log":
            # New flow: write to file + update graph index
            return await self._encode_log(
                message, evaluation, category, tenant_id, user_id, session_id
            )
        elif category == "reconsolidation":
            # Reconsolidation flow: update existing nodes
            return await self._encode_reconsolidation(
                message, evaluation, tenant_id, user_id, session_id
            )
        elif category == "prospective":
            # Prospective memory flow: create trigger nodes
            return await self._encode_prospective(
                message, evaluation, tenant_id, user_id, session_id
            )
        elif category == "forget":
            # Forget flow: suppress nodes
            return await self._encode_forget(
                message, evaluation, tenant_id, user_id, session_id
            )
        else:
            logger.warning("Unknown category '%s', defaulting to cognition", category)
            return await self._encode_cognition(
                message, evaluation, tenant_id, user_id, session_id, working_memory
            )

    async def _encode_cognition(
        self,
        message: str,
        evaluation: Dict[str, Any],
        tenant_id: str,
        user_id: str,
        session_id: str,
        working_memory: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Original cognition encoding flow (v2)."""

        # Step 1: Coarse extraction — get raw entities and relations
        extraction = await self._extract_raw(message, working_memory, evaluation)
        raw_entities = extraction.get("entities", [])
        raw_relations = extraction.get("relations", [])

        # Step 1.5: Smart entity resolution (LLM-driven)
        raw_entities = await self._smart_resolve_entities(
            raw_entities, tenant_id, user_id, message
        )

        if not raw_entities:
            logger.info("No entities extracted, skipping encode")
            return {"skipped": True, "reason": "no_entities"}

        # Step 2-4: Resolve each entity (tag归属 + 去重 + 关系构建)
        resolved_entities = []
        all_new_relations = list(raw_relations)  # Start with raw relations
        # Build name mapping: original_name → final_name (for relation fixup)
        name_mapping: Dict[str, str] = {}

        for raw_entity in raw_entities:
            name = raw_entity.get("name", "").strip()
            if not name:
                continue

            resolution = await self._resolve_entity(
                raw_entity, tenant_id, user_id
            )

            final_name = resolution.get("final_name", name)
            # Track mapping from original extracted name to resolved name
            if name != final_name:
                name_mapping[name] = final_name

            resolved_entities.append({
                "name": final_name,
                "tags": resolution.get("resolved_tags", raw_entity.get("tags", [])),
                "zone": raw_entity.get("zone", "semantic"),
                "summary": resolution.get("summary_update") or raw_entity.get("summary", ""),
                "properties": {
                    **raw_entity.get("properties", {}),
                    **resolution.get("properties_update", {}),
                },
                "existing_id": resolution.get("existing_id"),
                "action": resolution.get("action", "create"),
                "aliases_to_add": resolution.get("aliases_to_add", []),
            })

            # Collect new relations from resolution
            for rel in resolution.get("new_relations", []):
                all_new_relations.append(rel)

        # Fix P3+P4: Replace alias/raw names in relations with final resolved names
        if name_mapping:
            for rel in all_new_relations:
                from_name = rel.get("from_name", "")
                to_name = rel.get("to_name", "")
                if from_name in name_mapping:
                    rel["from_name"] = name_mapping[from_name]
                if to_name in name_mapping:
                    rel["to_name"] = name_mapping[to_name]

        # Step 5: Assemble and write memory unit
        importance = self._compute_importance(evaluation)
        memory_unit = {
            "id": str(uuid.uuid4()),
            "type": "memory",
            "message": message,
            "entities": resolved_entities,
            "relations": all_new_relations,
            "fact_type": extraction.get("fact_type", "simple"),
            "evaluation": evaluation,
            "importance": importance,
            "emotion_type": evaluation.get("emotion_type", "neutral"),
            "emotional_intensity": evaluation.get("emotional_intensity", 0),
            "encode_priority": evaluation.get("encode_priority", "low"),
            "tenant_id": tenant_id,
            "user_id": user_id,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "archived": False,
        }

        unit_id = self.buffer.write(tenant_id, user_id, session_id, memory_unit)
        memory_unit["id"] = unit_id

        # Generate embedding for buffer unit (async, fire-and-forget style)
        try:
            from server.engine.embedding_client import get_embedding
            import numpy as np
            emb_text = f"{message}"
            embedding = await get_embedding(emb_text, type_="db")
            if any(v != 0.0 for v in embedding[:10]):
                self.buffer.update_embedding(unit_id, np.array(embedding, dtype=np.float32).tobytes())
        except Exception as e:
            logger.warning("Failed to generate buffer embedding: %s", e)

        logger.info(
            "Encoded memory unit %s (priority=%s, entities=%d, relations=%d)",
            unit_id,
            evaluation.get("encode_priority"),
            len(resolved_entities),
            len(all_new_relations),
        )
        return memory_unit

    async def _encode_log(
        self,
        message: str,
        evaluation: Dict[str, Any],
        category: str,
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Log encoding flow (v3): write to file + update graph index.

        Args:
            message: Log message content
            evaluation: Evaluation dict (contains category, target_entity)
            category: Log category (log_diet, log_exercise, etc.)
            tenant_id: Tenant ID
            user_id: User ID
            session_id: Session ID

        Returns:
            Dict with keys: type="log", file_path, log_date, target_entity_updated
        """
        fuzzy_entities = evaluation.get("target_entities") or []

        # 4-way mapping: fuzzy entity names → precise graph nodes
        mapped_nodes: Dict[str, List[Node]] = {}
        if fuzzy_entities:
            mapped_nodes = await self._map_entities_to_nodes(
                fuzzy_entities, tenant_id, user_id, context=message
            )

        # Resolve precise names for log_writer (use best-matched node name, else original)
        precise_names = []
        for name in fuzzy_entities:
            nodes = mapped_nodes.get(name, [])
            precise_names.append(nodes[0].name if nodes else name)

        primary_entity = precise_names[0] if precise_names else None

        # Write log to file and update graph index
        result = await self.log_writer.write_log(
            category=category,
            message=message,
            target_entity=primary_entity,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        file_path = result.get("file_path", "")
        entity_label = "、".join(precise_names) if precise_names else ""
        summary_for_buffer = f"[{entity_label}] {message} (详见: {file_path})" if entity_label else message

        buffer_unit = {
            "id": str(uuid.uuid4()),
            "type": "log_index",
            "message": summary_for_buffer,
            "category": category,
            "target_entities": precise_names,
            "fuzzy_entities": fuzzy_entities,
            "file_path": file_path,
            "entities": [],
            "relations": [],
            "importance": self._compute_importance(evaluation),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.buffer.write(tenant_id, user_id, session_id, buffer_unit)

        logger.info(
            "Encoded log entry (category=%s, precise_targets=%s, file=%s)",
            category, precise_names, file_path
        )

        return {
            "type": "log",
            "category": category,
            "target_entities": precise_names,
            "file_path": result.get("file_path"),
            "log_date": result.get("log_date"),
            "target_entity_updated": result.get("target_entity_updated"),
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _encode_reconsolidation(
        self,
        message: str,
        evaluation: Dict[str, Any],
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Reconsolidation encoding flow: update existing nodes based on corrections.

        Args:
            message: Correction message content
            evaluation: Evaluation dict (contains category, target_entity, correction_type)
            tenant_id: Tenant ID
            user_id: User ID
            session_id: Session ID

        Returns:
            Dict with keys: type="reconsolidation", nodes_updated, correction_type
        """
        target_entities = evaluation.get("target_entities") or []
        correction_type = evaluation.get("correction_type", "correct")

        if not target_entities:
            logger.warning("Reconsolidation missing target_entities, skipping")
            return {"skipped": True, "reason": "missing_target_entities"}

        # 4-way mapping: fuzzy entity names → precise graph nodes
        mapped_nodes = await self._map_entities_to_nodes(
            target_entities, tenant_id, user_id, context=message
        )

        results = []
        for target_entity in target_entities:
            # Use best-matched node from 4-way mapping
            nodes = mapped_nodes.get(target_entity, [])

            if not nodes:
                # Auto-create the target entity if it doesn't exist
                logger.info("Target entity '%s' not found, auto-creating for reconsolidation", target_entity)
                from server.models.node import Node as NodeModel
                new_node = NodeModel(
                    name=target_entity,
                    tags=["计划"],
                    summary=message[:100],
                    zone="semantic",
                    importance=6.0,
                )
                node = await self.graph.create_node(new_node, tenant_id, user_id)
                nodes = [node]

            # Use the first matching node (most relevant)
            node = nodes[0]
            node_id = node.id

            # Step 2: Prepare updates based on correction_type
            updates = {}
            old_values = {}

            if correction_type == "correct":
                old_values["summary"] = node.summary
                old_values["content"] = node.content
                updates["summary"] = message
                updates["content"] = message

            elif correction_type == "supplement":
                old_values["content"] = node.content
                new_content = f"{node.content}\n{message}" if node.content else message
                updates["content"] = new_content
                updates["summary"] = f"{node.summary} | {message[:50]}" if node.summary else message[:50]

            elif correction_type == "reframe":
                old_values["emotional_tag"] = node.emotional_tag
                new_emotion = await self._extract_emotion(message)
                updates["emotional_tag"] = new_emotion

            # Step 3: Record correction history in properties
            correction_history = node.properties.get("_correction_history", [])
            correction_history.append({
                "timestamp": datetime.utcnow().isoformat(),
                "correction_type": correction_type,
                "old_values": old_values,
                "message": message,
                "session_id": session_id,
            })
            if len(correction_history) > 10:
                correction_history = correction_history[-10:]

            updates["properties"] = {**node.properties, "_correction_history": correction_history}

            # Step 4: Increment version and update
            updates["version"] = node.version + 1
            await self.graph.update_node(node_id, updates)

            logger.info(
                "Reconsolidation: updated node %s (entity=%s, type=%s, version=%d→%d)",
                node_id[:8], target_entity, correction_type, node.version, node.version + 1
            )
            results.append({
                "node_id": node_id,
                "target_entity": target_entity,
                "old_version": node.version,
                "new_version": node.version + 1,
            })

        return {
            "type": "reconsolidation",
            "correction_type": correction_type,
            "nodes_updated": len(results),
            "results": results,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _encode_prospective(
        self,
        message: str,
        evaluation: Dict[str, Any],
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Prospective memory encoding flow: create trigger nodes.

        Args:
            message: Original message content
            evaluation: Evaluation dict (contains trigger_type, trigger_value, action)
            tenant_id: Tenant ID
            user_id: User ID
            session_id: Session ID

        Returns:
            Dict with keys: type="prospective", node_id, trigger_type, trigger_value, action
        """
        trigger_type = evaluation.get("trigger_type")
        trigger_value = evaluation.get("trigger_value")
        action = evaluation.get("action")
        fuzzy_entities = evaluation.get("target_entities") or []

        if not trigger_type or not trigger_value or not action:
            logger.warning("Prospective memory missing required fields, skipping")
            return {"skipped": True, "reason": "missing_required_fields"}

        # 4-way mapping: map entities mentioned in the reminder to precise graph nodes
        linked_node_ids: List[str] = []
        linked_node_names: List[str] = []
        if fuzzy_entities:
            mapped_nodes = await self._map_entities_to_nodes(
                fuzzy_entities, tenant_id, user_id, context=message
            )
            for name in fuzzy_entities:
                nodes = mapped_nodes.get(name, [])
                if nodes:
                    linked_node_ids.append(nodes[0].id)
                    linked_node_names.append(nodes[0].name)

        # Create a memory node for the prospective memory
        node_id = str(uuid.uuid4())
        node = Node(
            id=node_id,
            name=f"提醒: {action[:30]}",
            tags=["计划", "提醒"],
            zone="procedural",
            summary=f"{trigger_type}触发器: {action}",
            content=message,
            importance=8.0,
            properties={
                "trigger_type": trigger_type,
                "trigger_value": trigger_value,
                "action": action,
                "status": "pending",
                "created_from": message,
                "session_id": session_id,
                "linked_entities": linked_node_names,
            },
        )

        # Write directly to graph (immediate availability, no buffer consolidation)
        await self.graph.create_node(node, tenant_id, user_id)

        # Create RELATED_TO relations to all linked entities
        from server.models.relation import Relation
        for linked_id in linked_node_ids:
            try:
                rel = Relation(
                    from_id=node_id,
                    to_id=linked_id,
                    type="RELATED_TO",
                    description=f"提醒事项涉及此实体",
                )
                await self.graph.create_relation(rel)
            except Exception as rel_err:
                logger.warning("Failed to create relation for prospective node: %s", rel_err)

        # Also write to buffer for retriever discoverability
        buffer_unit = {
            "id": str(uuid.uuid4()),
            "type": "prospective_index",
            "message": f"[提醒] {action} (触发条件: {trigger_value})",
            "category": "prospective",
            "trigger_type": trigger_type,
            "trigger_value": trigger_value,
            "action": action,
            "node_id": node_id,
            "entities": [{"name": n} for n in linked_node_names],
            "relations": [],
            "importance": 8.0,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.buffer.write(tenant_id, user_id, session_id, buffer_unit)

        logger.info(
            "Encoded prospective memory (type=%s, trigger=%s, action=%s, node=%s, linked=%s)",
            trigger_type, trigger_value, action, node_id[:8], linked_node_names
        )

        return {
            "type": "prospective",
            "node_id": node_id,
            "trigger_type": trigger_type,
            "trigger_value": trigger_value,
            "action": action,
            "linked_entities": linked_node_names,
            "status": "pending",
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _encode_forget(
        self,
        message: str,
        evaluation: Dict[str, Any],
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Forget encoding flow: suppress nodes by marking them as suppressed.

        Args:
            message: Original message content
            evaluation: Evaluation dict (contains target_entity)
            tenant_id: Tenant ID
            user_id: User ID
            session_id: Session ID

        Returns:
            Dict with keys: type="forget", nodes_suppressed, target_entity
        """
        target_entities = evaluation.get("target_entities") or []

        if not target_entities:
            logger.warning("Forget missing target_entities, skipping")
            return {"skipped": True, "reason": "missing_target_entities"}

        # 4-way mapping: fuzzy entity names → precise graph nodes
        mapped_nodes = await self._map_entities_to_nodes(
            target_entities, tenant_id, user_id, context=message
        )

        total_suppressed = 0
        all_suppressed_ids = []

        for target_entity in target_entities:
            nodes = mapped_nodes.get(target_entity, [])

            if not nodes:
                logger.warning("Target entity '%s' not found for forgetting (all 4 methods)", target_entity)
                continue

            for node in nodes:
                node_id = node.id
                try:
                    updates = {
                        "status": "suppressed",
                        "retrieval_strength": 0.0,
                        "properties": {
                            **node.properties,
                            "_suppressed_at": datetime.utcnow().isoformat(),
                            "_suppressed_reason": message,
                            "_suppressed_session": session_id,
                        },
                    }
                    await self.graph.update_node(node_id, updates)
                    total_suppressed += 1
                    all_suppressed_ids.append(node_id)
                    logger.info(
                        "Suppressed node %s (entity=%s) via forget command",
                        node_id[:8], node.name
                    )
                except Exception as e:
                    logger.warning("Failed to suppress node %s: %s", node_id, e)

        if total_suppressed == 0:
            return {"skipped": True, "reason": "suppression_failed", "target_entities": target_entities}

        logger.info(
            "Forget: suppressed %d nodes (entities=%s)",
            total_suppressed, target_entities
        )

        return {
            "type": "forget",
            "target_entities": target_entities,
            "nodes_suppressed": total_suppressed,
            "suppressed_ids": all_suppressed_ids,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _extract_emotion(self, message: str) -> Dict[str, Any]:
        """
        Extract emotional tag from a message using LLM.

        Returns:
            Dict with keys: type (joy/sadness/anger/fear/surprise/neutral), intensity (0-10)
        """
        system_prompt = """\
You are an emotion analyzer. Extract the emotional tone from the message.

Return ONLY valid JSON:
{
  "type": "joy" | "sadness" | "anger" | "fear" | "surprise" | "neutral",
  "intensity": 0-10
}
"""
        user_prompt = f'Message:\n"""\n{message}\n"""'

        try:
            result = await call_llm_json(system_prompt, user_prompt, temperature=0.1)
            emotion_type = result.get("type", "neutral")
            intensity = float(result.get("intensity", 0))

            # Validate
            valid_types = {"joy", "sadness", "anger", "fear", "surprise", "neutral"}
            if emotion_type not in valid_types:
                emotion_type = "neutral"
            if not (0 <= intensity <= 10):
                intensity = 0

            return {"type": emotion_type, "intensity": intensity}
        except Exception as e:
            logger.warning("Emotion extraction failed: %s", e)
            return {"type": "neutral", "intensity": 0}

    async def generate_session_summary(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Generate a structured summary from the buffer's encoded memory units.

        Instead of re-processing raw conversation text, this reads the
        already-encoded memory units (entities, relations, importance, etc.)
        produced by the hippocampal encoding pipeline during this session.
        """
        # Read all memory units for this session from the buffer
        session_units = self.buffer.read_by_session(session_id)
        # Filter to actual memory units (exclude previous summaries)
        memory_units = [u for u in session_units if u.get("type") == "memory"]

        if not memory_units:
            logger.info("No memory units in session %s, skipping summary", session_id)
            return {}

        # Build a compact representation of each unit for the LLM
        unit_summaries = []
        for u in memory_units:
            entity_names = [e.get("name", "") for e in u.get("entities", []) if e.get("action") != "skip"]
            relation_descs = [
                f"{r.get('from_name', '?')} --[{r.get('type', '?')}]--> {r.get('to_name', '?')}"
                for r in u.get("relations", [])
            ]
            unit_summaries.append({
                "message": u.get("message", ""),
                "entities": entity_names,
                "relations": relation_descs,
                "importance": u.get("importance", 0),
                "emotion": u.get("emotion_type", "neutral"),
                "emotional_intensity": u.get("emotional_intensity", 0),
            })

        user_prompt = (
            f"本次会话共编码 {len(memory_units)} 条记忆单元：\n"
            f"{json.dumps(unit_summaries, ensure_ascii=False, indent=2)}"
        )

        try:
            summary_data = await call_llm_json(_SUMMARY_SYSTEM, user_prompt)
        except Exception as e:
            logger.error("Session summary LLM call failed: %s", e)
            summary_data = {
                "topics": [], "key_entities": [],
                "key_conclusions": [], "pending_points": [],
                "emotional_arc": "neutral", "summary_text": "Summary generation failed.",
            }

        summary_unit = {
            "id": str(uuid.uuid4()),
            "type": "session_summary",
            "session_id": session_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "topics": summary_data.get("topics", []),
            "key_entities": summary_data.get("key_entities", []),
            "key_conclusions": summary_data.get("key_conclusions", []),
            "pending_points": summary_data.get("pending_points", []),
            "emotional_arc": summary_data.get("emotional_arc", "neutral"),
            "summary_text": summary_data.get("summary_text", ""),
            "importance": 7.0,
            "timestamp": datetime.utcnow().isoformat(),
            "archived": False,
        }

        unit_id = self.buffer.write(tenant_id, user_id, session_id, summary_unit)
        summary_unit["id"] = unit_id
        logger.info("Generated session summary %s for session %s (%d units)",
                     unit_id, session_id, len(memory_units))
        return summary_unit

    # ------------------------------------------------------------------
    # 模糊实体 → 精确图谱节点 映射（4路并行）
    # ------------------------------------------------------------------

    async def _map_entities_to_nodes(
        self,
        entity_names: List[str],
        tenant_id: str,
        user_id: str,
        context: str = "",
    ) -> Dict[str, List[Node]]:
        """
        将感知器提取的模糊实体名映射到图谱中的精确节点，4路并行：
          1. 精确名称召回 (find_nodes_by_name)
          2. 模糊名称召回 (find_nodes_fuzzy)
          3. 向量相似度召回 (vector_search)
          4. LLM判断 (对方法1-3未命中的实体，传入全量节点名称由LLM判断)

        Returns:
            {entity_name: [Node, ...]}  按置信度排列，最高置信在前。
            未找到匹配时对应 []。
        """
        if not entity_names:
            return {}

        async def _vector_search_for(name: str) -> List[Node]:
            try:
                from server.engine.embedding_client import get_embedding
                emb = await get_embedding(name, type_="db")
                raw = await self.graph.vector_search(emb, top_k=5, min_score=0.72)
                nodes = []
                for r in raw:
                    node_dict = r.get("node", {})
                    # 过滤租户隔离
                    if node_dict.get("tenant_id") != tenant_id or node_dict.get("user_id") != user_id:
                        continue
                    if node_dict.get("status") == "suppressed":
                        continue
                    try:
                        nodes.append(Node.from_neo4j_props(node_dict))
                    except Exception:
                        pass
                return nodes
            except Exception:
                return []

        async def _search_one(name: str) -> Tuple[str, List[Node]]:
            exact, fuzzy, vector = await asyncio.gather(
                self.graph.find_nodes_by_name(name, tenant_id, user_id),
                self.graph.find_nodes_fuzzy(name, tenant_id, user_id),
                _vector_search_for(name),
            )
            seen: Dict[str, Tuple[Node, int]] = {}
            # 优先级：精确(0) > 模糊(1) > 向量(2)
            for priority, nodes in enumerate([exact, fuzzy, vector]):
                for node in nodes:
                    if node.id not in seen:
                        seen[node.id] = (node, priority)
            ranked = sorted(seen.values(), key=lambda x: x[1])
            return name, [n for n, _ in ranked]

        # 所有实体并行执行方法1-3
        results = await asyncio.gather(*[_search_one(name) for name in entity_names])
        mapping: Dict[str, List[Node]] = dict(results)

        # 方法4：对1-3均未命中的实体，用LLM在全量节点名称中判断
        unresolved = [name for name, nodes in mapping.items() if not nodes]
        if unresolved:
            try:
                all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
                all_node_names = [n.name for n in all_nodes]
                all_nodes_by_name = {n.name: n for n in all_nodes}
                if all_node_names:
                    llm_matches = await self._llm_entity_name_judgment(
                        unresolved, all_node_names, context
                    )
                    for entity_name, matched_names in llm_matches.items():
                        nodes = [all_nodes_by_name[n] for n in matched_names if n in all_nodes_by_name]
                        if nodes:
                            mapping[entity_name] = nodes
                            logger.debug(
                                "LLM mapped entity '%s' → %s",
                                entity_name, [n.name for n in nodes]
                            )
            except Exception as e:
                logger.warning("LLM entity name judgment failed: %s", e)

        return mapping

    async def _llm_entity_name_judgment(
        self,
        fuzzy_names: List[str],
        all_node_names: List[str],
        context: str = "",
    ) -> Dict[str, List[str]]:
        """
        LLM批量判断：给定模糊实体列表和图谱全量节点名称，返回匹配关系。
        处理全称/简称/昵称/称谓等变体。
        """
        # 节点名称过多时截断，避免 token 爆炸
        node_list_text = "\n".join(f"- {n}" for n in all_node_names)
        context_line = f"\n上下文: {context[:200]}" if context else ""

        system_prompt = """\
你是知识图谱实体名称匹配专家。
给定一组从用户消息中提取的模糊实体名称，以及图谱中所有已有节点名称，
判断哪些已有节点与哪些模糊实体是同一个实体。
考虑：全称/简称、昵称/真名、称谓变体（如"凡哥"对应"刘凡"）、中英文混用。

返回格式（仅JSON）：
{
  "matches": {
    "模糊实体名": ["匹配的节点名1", "匹配的节点名2"],
    ...
  }
}
没有把握的匹配返回空列表 []，宁缺毋滥。
"""
        user_prompt = (
            f"模糊实体（需要映射）：\n{json.dumps(fuzzy_names, ensure_ascii=False)}"
            f"\n\n图谱已有节点名称：\n{node_list_text}"
            f"{context_line}"
        )

        try:
            result = await call_llm_json(system_prompt, user_prompt, temperature=0.1)
            matches = result.get("matches", {})
            return {k: v if isinstance(v, list) else [] for k, v in matches.items()}
        except Exception as e:
            logger.warning("_llm_entity_name_judgment failed: %s", e)
            return {}

    # ------------------------------------------------------------------
    # Entity filtering
    # ------------------------------------------------------------------

    async def _smart_resolve_entities(
        self,
        raw_entities: List[Dict[str, Any]],
        tenant_id: str,
        user_id: str,
        message_context: str,
    ) -> List[Dict[str, Any]]:
        """
        LLM-driven intelligent entity resolution.

        For each candidate entity, the LLM decides:
        - create: New entity, not in graph
        - merge: Same as existing entity, merge to existing node
        - update: New info for existing entity, update existing node
        - skip: Not worth adding to graph (trivial details, numbers, food, etc.)

        Args:
            raw_entities: Coarsely extracted candidate entities
            tenant_id: Tenant ID
            user_id: User ID
            message_context: Original user message for context

        Returns:
            List of entities with resolution decisions attached
        """
        if not raw_entities:
            return []

        # Step 1: 4路并行召回每个候选实体的相关图谱节点
        # （精确名称 + 模糊名称 + 向量相似度 + LLM判断）
        entity_names = [e.get("name", "") for e in raw_entities if e.get("name")]
        mapped_nodes = await self._map_entities_to_nodes(
            entity_names, tenant_id, user_id, context=message_context
        )

        # P6: Also check recent buffer entries for entities not yet in graph
        # This handles consecutive messages where entity A is encoded but not
        # yet consolidated, and entity B references A
        buffer_entities = self._get_recent_buffer_entities(tenant_id, user_id)

        # 补充标签维度召回（_map_entities_to_nodes 不含 tag 搜索）
        # 标签召回用于让 LLM 了解图谱中同类实体，辅助 skip 判断
        tag_candidates: Dict[str, List[Node]] = {}
        tag_search_tasks = []
        for entity in raw_entities:
            tags = entity.get("tags", [])
            name = entity.get("name", "")
            if tags:
                tag_search_tasks.append((name, self.graph.find_nodes_by_tags(
                    tags, tenant_id, user_id,
                    expand_hierarchy=True, tag_dict=self.tag_dict,
                )))
        if tag_search_tasks:
            tag_results = await asyncio.gather(*[t for _, t in tag_search_tasks], return_exceptions=True)
            for (name, _), result in zip(tag_search_tasks, tag_results):
                if not isinstance(result, Exception):
                    tag_candidates[name] = [n for n in result if n.status == "active"][:3]

        # 合并：4路召回结果 + 标签召回，去重，每实体限5个候选
        existing_entities_map: Dict[str, List[Node]] = {}
        for entity in raw_entities:
            name = entity.get("name", "")
            seen_ids: set = set()
            merged: List[Node] = []
            for node in (mapped_nodes.get(name, []) + tag_candidates.get(name, [])):
                if node.id not in seen_ids and len(merged) < 5:
                    seen_ids.add(node.id)
                    merged.append(node)
            existing_entities_map[name] = merged

        # Step 2: 构建 LLM prompt
        candidates_json = [
            {"name": e.get("name", ""), "tags": e.get("tags", []), "summary": e.get("summary", "")}
            for e in raw_entities
        ]
        existing_json = {
            name: [
                {"name": n.name, "tags": n.tags, "summary": n.summary or "", "aliases": n.aliases}
                for n in nodes
            ]
            for name, nodes in existing_entities_map.items()
        }
        # P6: Inject buffer entities for candidates with no graph matches
        if buffer_entities:
            for entity in raw_entities:
                name = entity.get("name", "")
                if name and not existing_json.get(name):
                    # Check if any buffer entity matches this candidate
                    name_lower = name.lower()
                    for be in buffer_entities:
                        be_name = be.get("name", "").lower()
                        if be_name and (name_lower in be_name or be_name in name_lower):
                            existing_json.setdefault(name, []).append({
                                "name": be["name"],
                                "tags": be.get("tags", []),
                                "summary": be.get("summary", ""),
                                "aliases": be.get("aliases_to_add", []),
                                "_source": "buffer",
                            })

        system_prompt = """\
你是知识图谱实体管理专家。用户消息产生了一批候选实体，你需要决定每个实体如何处理。

## 决策选项

**create** — 真正的新实体，图谱中不存在
**merge** — 与已有实体是同一个（含昵称、简称、称谓变体，如"凡哥"→"刘凡"）
  必须指定 target（已有实体名称）
**update** — 已有实体，但本次提及带来了新信息
  必须指定 target（已有实体名称）
**skip** — 不值得入图谱，包括：
  - 纯数字、单位（"600大卡"、"90kg"、"5公里"）
  - 具体食物（"苹果"、"牛肉面"）— 属于日志，不是知识图谱实体
  - 通用常识（"地球"、"太阳"、"Python语言"本身）
  - 临时调试信息
  - 代词（"我"、"用户"）若用户节点已存在

## 判断原则
- 人物、组织、项目、计划、决策、里程碑 → 通常 create 或 update
- 食物、数字、通用概念 → 通常 skip
- 有名称变体匹配（昵称/全称/别名）→ 优先 merge，不要重复创建
- 有新信息但实体已存在 → update，不要 create
- 不确定 → skip（防止图谱膨胀）

## 返回格式（仅 JSON 数组）
[
  {
    "name": "候选实体名",
    "decision": "create|merge|update|skip",
    "target": "目标已有实体名（merge/update时必填，其余为null）",
    "reason": "一句话理由"
  }
]
"""

        user_prompt = (
            f'用户消息上下文："{message_context}"\n\n'
            f"候选实体：\n{json.dumps(candidates_json, ensure_ascii=False, indent=2)}\n\n"
            f"图谱中相关已有实体（4路召回结果）：\n{json.dumps(existing_json, ensure_ascii=False, indent=2)}"
        )

        # Step 3: LLM 判断
        try:
            result = await call_llm_json(system_prompt, user_prompt, temperature=0.1)
            decisions = result if isinstance(result, list) else result.get("decisions", [])
        except Exception as exc:
            logger.error("LLM entity resolution failed: %s. Defaulting to skip all.", exc)
            decisions = [
                {"name": e.get("name", ""), "decision": "skip", "target": None, "reason": "LLM error"}
                for e in raw_entities
            ]

        # Step 4: 附加决策并过滤掉 skip 实体
        # 同时将已召回的目标 Node 挂到 entity 上，供 _resolve_entity 直接复用，避免重复查询
        decision_map = {d.get("name", ""): d for d in decisions}
        resolved = []
        for entity in raw_entities:
            name = entity.get("name", "")
            decision = decision_map.get(name, {"decision": "skip", "target": None, "reason": "no decision"})
            entity["resolution"] = decision
            # 对 merge/update，把已召回的目标 Node 缓存到 entity 上
            target_name = decision.get("target") or ""
            if decision.get("decision") in ("merge", "update") and target_name:
                for node in existing_entities_map.get(name, []):
                    if node.name == target_name:
                        entity["_resolved_node"] = node
                        break
            if decision.get("decision") != "skip":
                resolved.append(entity)
            else:
                logger.debug("Skipped entity '%s': %s", name, decision.get("reason", ""))

        return resolved

    def _get_recent_buffer_entities(
        self, tenant_id: str, user_id: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Extract entity info from recent buffer entries (not yet consolidated).

        This allows consecutive messages to reference entities that were encoded
        in the current session but haven't been written to the graph yet.
        """
        try:
            recent_units = self.buffer.read_recent(tenant_id, user_id, limit=limit)
            entities = []
            seen_names: set = set()
            for unit in recent_units:
                for ent in unit.get("entities", []):
                    name = ent.get("name", "")
                    if name and name not in seen_names:
                        seen_names.add(name)
                        entities.append(ent)
            return entities
        except Exception as e:
            logger.warning("Failed to read recent buffer entities: %s", e)
            return []

    async def _strict_dedup_check(self, entity_name: str, tenant_id: str, user_id: str) -> Optional[Node]:
        """
        Strict deduplication check before writing to buffer.

        Checks:
        1. Exact name match
        2. Alias match
        3. Substring match (e.g., "海马体缓冲区" contains "海马体")

        Args:
            entity_name: Entity name to check
            tenant_id: Tenant ID
            user_id: User ID

        Returns:
            Existing node if found, None otherwise
        """
        try:
            # 1. Exact name match
            matches = await self.graph.find_nodes_by_name(entity_name, tenant_id, user_id)
            if matches:
                return matches[0]

            # 2. Alias match
            matches = await self.graph.find_nodes_by_alias(entity_name, tenant_id, user_id)
            if matches:
                return matches[0]

            # 3. Substring match — 收紧条件：短串至少3字符，且长度占比 >= 50%
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            entity_lower = entity_name.lower()

            for node in all_nodes:
                node_lower = node.name.lower()
                if entity_lower in node_lower or node_lower in entity_lower:
                    shorter = min(len(entity_lower), len(node_lower))
                    longer = max(len(entity_lower), len(node_lower))
                    if shorter >= 3 and shorter / longer >= 0.5:
                        logger.debug("Substring match found: '%s' <-> '%s'", entity_name, node.name)
                        return node

            return None

        except Exception as e:
            logger.warning("Strict dedup check failed for '%s': %s", entity_name, e)
            return None

    # ------------------------------------------------------------------
    # Step 1: Coarse extraction
    # ------------------------------------------------------------------

    async def _extract_raw(
        self,
        message: str,
        working_memory: Optional[Dict[str, Any]],
        evaluation: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """LLM粗提取：从消息中提取原始实体和关系，利用 perceiver/evaluator 的全部上下文。"""
        context_parts = []

        if working_memory:
            raw = working_memory.get("raw", {})
            profile = raw.get("user_profile", {})
            if profile:
                context_parts.append(f"用户画像: {profile}")
            if working_memory.get("user_goals"):
                goals = "; ".join(working_memory["user_goals"])
                context_parts.append(f"活跃目标: {goals}")
            events = raw.get("recent_events", [])
            if events:
                ev_text = "; ".join(e.get("summary") or e.get("name", "") for e in events[:5])
                context_parts.append(f"近期事件: {ev_text}")
            session_msgs = working_memory.get("session_messages", [])
            if session_msgs:
                lines = " | ".join(session_msgs[-3:])
                context_parts.append(f"本session上文: {lines}")

        if evaluation:
            hint_entities = evaluation.get("target_entities") or []
            if hint_entities:
                context_parts.append(f"感知器已提取的模糊实体（提取时应重点关注）: {hint_entities}")
            category = evaluation.get("category", "")
            if category:
                context_parts.append(f"消息类别: {category}")

        context_block = ""
        if context_parts:
            context_block = "\n\n上下文信息（用于消歧和实体解析）：\n" + "\n".join(context_parts)

        user_prompt = f'消息：\n"""\n{message}\n"""{context_block}'
        try:
            return await call_llm_json(_EXTRACT_SYSTEM, user_prompt)
        except Exception as e:
            logger.error("Raw extraction failed: %s", e)
            return {"entities": [], "relations": []}

    # ------------------------------------------------------------------
    # Step 2-4: Entity resolution (合并调用)
    # ------------------------------------------------------------------

    async def _resolve_entity(
        self,
        raw_entity: Dict[str, Any],
        tenant_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        对单个实体执行完整解析：Tag归属 + 图谱节点定位 + 关系/别名/属性构建 + 干扰检测。

        优化：复用 _smart_resolve_entities 的先验决策（entity["resolution"]），
        有先验时直接精确查找目标节点，跳过 strict_dedup_check 和 find_active_nodes 全扫。
        """
        name = raw_entity.get("name", "").strip()
        raw_tags = raw_entity.get("tags", [])
        prior = raw_entity.get("resolution", {})
        prior_decision = prior.get("decision", "")
        prior_target = prior.get("target") or ""

        # --- Step 1: 定位已有节点（复用先验，避免重复搜索）---
        same_tag_entities: List[Dict[str, Any]] = []

        if prior_decision in ("merge", "update") and prior_target:
            # 优先使用 _smart_resolve_entities 已缓存的 Node，避免重复查询
            cached_node: Optional[Node] = raw_entity.get("_resolved_node")
            if cached_node is None:
                # 缓存未命中（target 名称不在召回结果中），降级查询
                target_nodes = await self.graph.find_nodes_by_name(prior_target, tenant_id, user_id)
                if not target_nodes:
                    target_nodes = await self.graph.find_nodes_fuzzy(prior_target, tenant_id, user_id)
                cached_node = target_nodes[0] if target_nodes else None

            if cached_node:
                same_tag_entities = [{
                    "name": cached_node.name,
                    "tags": cached_node.tags,
                    "zone": cached_node.zone,
                    "summary": cached_node.summary or "",
                    "id": cached_node.id,
                    "aliases": (cached_node.properties or {}).get("aliases", []),
                }]
                logger.debug(
                    "Prior resolution '%s'→'%s': found node %s (cached=%s)",
                    name, prior_target, cached_node.id[:8],
                    raw_entity.get("_resolved_node") is not None,
                )
            else:
                # 先验目标未找到，降级为 create
                logger.info("Prior target '%s' not found in graph, falling back to create", prior_target)
                prior_decision = "create"

        elif prior_decision == "create":
            # 先验已明确新实体 → 跳过所有搜索
            pass

        else:
            # 无先验（兜底）：原始 strict_dedup_check + 全量扫描
            fallback_existing_node = await self._strict_dedup_check(name, tenant_id, user_id)
            if fallback_existing_node:
                logger.info("Strict dedup: '%s' → '%s' (%s), will update",
                            name, fallback_existing_node.name, fallback_existing_node.id[:8])
                return {
                    "action": "update",
                    "final_name": fallback_existing_node.name,
                    "resolved_tags": fallback_existing_node.tags,
                    "existing_id": fallback_existing_node.id,
                    "aliases_to_add": [name] if name != fallback_existing_node.name else [],
                    "summary_update": raw_entity.get("summary"),
                    "properties_update": {},
                    "new_relations": [],
                    "reason": "strict dedup match",
                }
            # 全量扫描：按 tag overlap 或名称相似性过滤
            try:
                all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
                name_lower = name.lower()
                for node in all_nodes:
                    has_tag_overlap = bool(set(node.tags or []) & set(raw_tags))
                    node_name_lower = node.name.lower()
                    has_name_sim = (
                        name_lower in node_name_lower or
                        node_name_lower in name_lower
                    )
                    if has_tag_overlap or has_name_sim:
                        same_tag_entities.append({
                            "name": node.name,
                            "tags": node.tags,
                            "zone": node.zone,
                            "summary": node.summary or "",
                            "id": node.id,
                            "aliases": (node.properties or {}).get("aliases", []),
                        })
            except Exception as e:
                logger.warning("Failed to fetch same-tag entities: %s", e)

        # --- Step 2: Tag 归属（始终执行）---
        resolved_tags: List[str] = []
        for tag in raw_tags:
            similar = await self.tag_dict.find_similar(tag)
            if similar:
                canonical = (
                    similar.preferred_replacement
                    if similar.status == "deprecated" and similar.preferred_replacement
                    else similar.name
                )
                resolved_tags.append(canonical)
                self.tag_dict.increment_usage(canonical)
            else:
                new_tag = self.tag_dict.add_tag(tag)
                resolved_tags.append(new_tag.name)
                self.tag_dict.increment_usage(new_tag.name)

        # --- Step 3: LLM 详细解析（关系/别名/属性/摘要构建）---
        if not same_tag_entities and prior_decision != "merge":
            # 无候选节点且不是 merge → 直接 create
            return {
                "action": "create",
                "final_name": name,
                "resolved_tags": resolved_tags,
                "existing_id": None,
                "aliases_to_add": [],
                "summary_update": None,
                "properties_update": {},
                "new_relations": [],
                "reason": prior.get("reason") or "no existing entities found",
            }

        tag_taxonomy = self.tag_dict.get_hierarchy_tree_text()
        existing_list = "\n".join(
            f"- {e['name']} (id={e['id'][:8]}, tags={e['tags']}, "
            f"zone={e['zone']}, summary={e['summary'][:80]}, aliases={e.get('aliases', [])})"
            for e in same_tag_entities[:15]
        )

        # 将先验决策注入 prompt，引导 LLM 聚焦关系/别名构建而非重新决策
        prior_hint = ""
        if prior_decision in ("merge", "update") and prior_target:
            prior_hint = (
                f"\n\n【前置判断】上游已确认此实体应 {prior_decision} 到「{prior_target}」，"
                f"请在此基础上填写 aliases_to_add / summary_update / new_relations / properties_update，"
                f"action 字段返回 \"{prior_decision}\"，target_entity_name 返回 \"{prior_target}\"。"
            )

        user_prompt = (
            f"待解析实体：\n"
            f"  名称：\"{name}\"\n"
            f"  初步标签：{raw_tags}\n"
            f"  记忆区域：{raw_entity.get('zone', 'semantic')}\n"
            f"  摘要：{raw_entity.get('summary', '')}\n\n"
            f"图谱中的候选已有实体：\n{existing_list}\n\n"
            f"可用标签层级树：\n{tag_taxonomy}"
            f"{prior_hint}"
        )

        try:
            result = await call_llm_json(_RESOLVE_ENTITY_SYSTEM, user_prompt, temperature=0.1)
        except Exception as e:
            logger.warning("Entity resolution LLM failed for '%s': %s", name, e)
            return {
                "action": prior_decision if prior_decision in ("create", "merge", "update") else "create",
                "final_name": prior_target if prior_target else name,
                "resolved_tags": resolved_tags,
                "existing_id": same_tag_entities[0]["id"] if same_tag_entities else None,
                "aliases_to_add": [],
                "summary_update": None,
                "properties_update": {},
                "new_relations": [],
                "reason": f"LLM resolution failed: {e}",
            }

        action = result.get("action", prior_decision or "create")
        target_name = result.get("target_entity_name") or prior_target

        # Tag 标准化
        final_tags: List[str] = []
        for t in result.get("resolved_tags", resolved_tags):
            similar = await self.tag_dict.find_similar(t)
            if similar and similar.status == "active":
                final_tags.append(similar.name)
            else:
                new_tag = self.tag_dict.add_tag(t)
                final_tags.append(new_tag.name)

        # 确定 existing_id 和 final_name
        existing_id = None
        final_name = name
        if action in ("merge", "update") and target_name:
            for e in same_tag_entities:
                if e["name"] == target_name:
                    existing_id = e["id"]
                    final_name = target_name
                    break
            if not existing_id:
                action = "create"
                final_name = name

        resolution_result = {
            "action": action,
            "final_name": final_name,
            "resolved_tags": final_tags,
            "existing_id": existing_id,
            "aliases_to_add": result.get("aliases_to_add", []),
            "summary_update": result.get("summary_update"),
            "properties_update": result.get("properties_update", {}),
            "new_relations": result.get("new_relations", []),
            "reason": result.get("reason", ""),
        }

        # --- Step 4: 干扰检测（仅 update）---
        if action == "update" and existing_id:
            interference = await self._check_interference(
                existing_id, raw_entity, resolution_result, tenant_id, user_id
            )
            if interference:
                resolution_result["properties_update"] = {
                    **resolution_result.get("properties_update", {}),
                    **interference.get("properties_update", {}),
                }
                resolution_result["relations_to_invalidate"] = interference.get("relations_to_invalidate", [])

        return resolution_result

    # ------------------------------------------------------------------
    # Interference detection
    # ------------------------------------------------------------------

    async def _check_interference(
        self,
        existing_id: str,
        new_entity: Dict[str, Any],
        resolution: Dict[str, Any],
        tenant_id: str,
        user_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        检测新旧信息之间的干扰，判断是否存在矛盾或状态更新。

        Args:
            existing_id: 已存在的实体ID
            new_entity: 新提取的实体信息
            resolution: LLM解析结果
            tenant_id: 租户ID
            user_id: 用户ID

        Returns:
            Dict with interference handling instructions, or None if no interference
        """
        try:
            # Get the existing node
            existing_node = await self.graph.get_node(existing_id)
            if not existing_node:
                return None

            old_summary = existing_node.summary or ""
            new_summary = resolution.get("summary_update") or new_entity.get("summary", "")

            if not old_summary or not new_summary:
                return None

            # Use LLM to detect if there's a contradiction or state change
            system_prompt = """\
You are an interference detector for a memory system. Compare old and new information about the same entity.

Determine the relationship:
1. "contradiction" - New info directly contradicts old info (e.g., "works at A" vs "works at B")
2. "state_update" - New info represents a state change (e.g., "joined company" → "left company")
3. "complement" - New info adds to old info without conflict
4. "duplicate" - New info is essentially the same as old info

Return ONLY valid JSON:
{
  "relationship": "contradiction" | "state_update" | "complement" | "duplicate",
  "reason": "brief explanation",
  "affected_relation_types": ["WORKS_AT", "LOCATED_IN"]
}
"""
            user_prompt = f"""Entity: {existing_node.name}

Old information: {old_summary}

New information: {new_summary}

What is the relationship between old and new information?"""

            result = await call_llm_json(system_prompt, user_prompt, temperature=0.1)
            relationship = result.get("relationship", "complement")

            interference_result = {}

            if relationship == "contradiction":
                # Mark conflict for consolidator to resolve
                interference_result["properties_update"] = {
                    "_conflict_with": existing_id,
                    "_conflict_old_summary": old_summary,
                    "_conflict_new_summary": new_summary,
                    "_conflict_detected_at": datetime.utcnow().isoformat(),
                }
                logger.info("Detected contradiction for entity %s: %s", existing_node.name, result.get("reason"))

            elif relationship == "state_update":
                # Mark old relations as invalid and reduce retrieval strength
                affected_types = result.get("affected_relation_types", [])
                interference_result["relations_to_invalidate"] = affected_types

                # Reduce old node's retrieval strength by 50%
                new_strength = max(existing_node.retrieval_strength * 0.5, 0.1)
                await self.graph.update_node(existing_id, {
                    "retrieval_strength": new_strength,
                    "updated_at": datetime.utcnow().isoformat(),
                })

                logger.info("Detected state update for entity %s: %s (strength %.1f→%.1f)",
                           existing_node.name, result.get("reason"),
                           existing_node.retrieval_strength, new_strength)

            elif relationship == "duplicate":
                # No action needed, just log
                logger.debug("Detected duplicate information for entity %s", existing_node.name)

            return interference_result if interference_result else None

        except Exception as e:
            logger.warning("Interference detection failed for %s: %s", existing_id, e)
            return None

    # ------------------------------------------------------------------
    # Importance computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_importance(evaluation: Dict[str, Any]) -> float:
        """Compute a 0-10 importance score from the evaluation dict."""
        tr = float(evaluation.get("task_relevance", 5))
        ei = float(evaluation.get("emotional_intensity", 0))
        nv = float(evaluation.get("novelty", 5))
        return round(tr * 0.5 + ei * 0.3 + nv * 0.2, 2)
