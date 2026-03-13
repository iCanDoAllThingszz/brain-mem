"""
Encoder engine component for the brain-memory service.
Corresponds to the hippocampus in the human brain.
Transforms raw messages into structured memory units and writes them to the buffer.

v2: Entity lifecycle management — tag归属 + 去重 + 关系构建 合并为单次LLM调用。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from server.engine.llm_client import call_llm, call_llm_json
from server.models.node import Node
from server.storage.buffer import EncoderBuffer
from server.storage.graph import GraphStore
from server.storage.tag_dict import TagDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Step 1: 粗提取 — 从消息中提取原始实体和关系
# ---------------------------------------------------------------------------
_EXTRACT_SYSTEM = """\
You are an information extraction engine. Extract entities and relationships \
from the given message. Keep it concise.

Rules:
- Extract named entities: people, organizations, places, concepts, events, decisions, plans.
- Assign a memory zone: semantic / episodic / procedural / emotional.
- Assign 1-2 preliminary tags per entity (Chinese labels preferred).
- Ignore garbled/encoded names (like "Gbusrw Jflvnkmwi") — display artifacts.
- Relation types: UPPER_SNAKE_CASE (e.g., WORKS_AT, DECIDED_TO).

Return ONLY valid JSON:
{
  "entities": [
    {"name": "entity name", "tags": ["tag1"], "zone": "semantic", "summary": "one sentence"}
  ],
  "relations": [
    {"from_name": "A", "to_name": "B", "type": "REL_TYPE", "description": "desc"}
  ]
}
"""

# ---------------------------------------------------------------------------
# Step 2+3+4 合并: 实体解析 — tag归属 + 去重 + 关系构建 一次LLM调用
# ---------------------------------------------------------------------------
_RESOLVE_ENTITY_SYSTEM = """\
You are a knowledge graph entity resolver. Given a newly extracted entity and \
the existing entities in the graph that share similar tags, decide what to do.

You must decide ONE of three actions:
1. "merge" — The new entity is the same as an existing entity. Merge into it.
2. "update" — The new entity adds new information to an existing entity. Update it.
3. "create" — The new entity is genuinely new. Create it.

Tag assignment rules:
- Use the provided tag taxonomy. Pick the best matching tag(s).
- If no existing tag fits, propose a new tag that is GENERAL enough to be reused \
  (e.g., "医疗" not "牙科手术", "交通" not "地铁3号线").
- Each entity should have 1-2 tags maximum.

Return ONLY valid JSON:
{
  "action": "merge" | "update" | "create",
  "resolved_tags": ["tag1", "tag2"],
  "target_entity_name": "name of existing entity to merge/update into (null if create)",
  "aliases_to_add": ["alias1"],
  "summary_update": "updated summary text (null if no change)",
  "properties_update": {},
  "new_relations": [
    {"from_name": "A", "to_name": "B", "type": "REL_TYPE", "description": "desc"}
  ],
  "reason": "one-sentence explanation"
}
"""

# ---------------------------------------------------------------------------
# Session summary prompt (unchanged)
# ---------------------------------------------------------------------------
_SUMMARY_SYSTEM = """\
You are a session summarizer for an AI agent's memory system. \
Summarize the conversation into a concise structured summary.

Return ONLY valid JSON:
{
  "topics": ["topic1", "topic2"],
  "key_conclusions": ["conclusion1"],
  "pending_points": ["unresolved1"],
  "emotional_arc": "positive|negative|neutral|mixed",
  "summary_text": "2-3 sentence summary"
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
    """

    def __init__(self, graph: GraphStore, tag_dict: TagDict, buffer: EncoderBuffer) -> None:
        self.graph = graph
        self.tag_dict = tag_dict
        self.buffer = buffer

    async def encode_message(
        self,
        message: str,
        evaluation: Dict[str, Any],
        tenant_id: str,
        user_id: str,
        session_id: str,
        working_memory: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Encode a message into a structured memory unit."""

        # Step 0: Dedup check against recent buffer
        recent = self.buffer.read_recent(tenant_id, user_id, limit=20)
        for existing in recent:
            if existing.get("message", "").strip() == message.strip():
                logger.info("Skipping duplicate message: %.60s", message)
                return {"skipped": True, "reason": "duplicate"}

        # Step 1: Coarse extraction — get raw entities and relations
        extraction = await self._extract_raw(message, working_memory)
        raw_entities = extraction.get("entities", [])
        raw_relations = extraction.get("relations", [])

        if not raw_entities:
            logger.info("No entities extracted, skipping encode")
            return {"skipped": True, "reason": "no_entities"}

        # Step 2-4: Resolve each entity (tag归属 + 去重 + 关系构建)
        resolved_entities = []
        all_new_relations = list(raw_relations)  # Start with raw relations

        for raw_entity in raw_entities:
            name = raw_entity.get("name", "").strip()
            if not name:
                continue

            resolution = await self._resolve_entity(
                raw_entity, tenant_id, user_id
            )

            resolved_entities.append({
                "name": resolution.get("final_name", name),
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
        logger.info(
            "Encoded memory unit %s (priority=%s, entities=%d, relations=%d)",
            unit_id,
            evaluation.get("encode_priority"),
            len(resolved_entities),
            len(all_new_relations),
        )
        return memory_unit

    async def generate_session_summary(
        self,
        conversation_history: List[Dict[str, Any]],
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """Generate a structured summary for a completed session."""
        formatted = "\n".join(
            f"[{msg.get('role', 'user')}]: {msg.get('content', '')}"
            for msg in conversation_history[-50:]
        )
        user_prompt = f'Conversation to summarize:\n"""\n{formatted}\n"""'

        try:
            summary_data = await call_llm_json(_SUMMARY_SYSTEM, user_prompt)
        except Exception as e:
            logger.error("Session summary LLM call failed: %s", e)
            summary_data = {
                "topics": [], "key_conclusions": [], "pending_points": [],
                "emotional_arc": "neutral", "summary_text": "Summary generation failed.",
            }

        summary_unit = {
            "id": str(uuid.uuid4()),
            "type": "session_summary",
            "session_id": session_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "topics": summary_data.get("topics", []),
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
        logger.info("Generated session summary %s for session %s", unit_id, session_id)
        return summary_unit

    # ------------------------------------------------------------------
    # Step 1: Coarse extraction
    # ------------------------------------------------------------------

    async def _extract_raw(
        self,
        message: str,
        working_memory: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """LLM粗提取：从消息中提取原始实体和关系。"""
        context_hint = ""
        if working_memory and working_memory.get("context"):
            context_hint = f"\nSession context:\n{working_memory['context'][:400]}"

        user_prompt = f'Message:\n"""\n{message}\n"""{context_hint}'
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
        对单个实体执行完整的解析流程：
        1. Tag归属：查tag字典，确定实体应归入哪个tag
        2. 同类检索：按tag去图谱检索同类实体
        3. LLM判断：create/merge/update + 关系构建（一次调用）
        """
        name = raw_entity.get("name", "").strip()
        raw_tags = raw_entity.get("tags", [])

        # --- Step 2: Tag归属 ---
        resolved_tags = []
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
                # No match — but don't blindly add. Check if it's too specific.
                # For now, add it but the LLM resolve step may override.
                new_tag = self.tag_dict.add_tag(tag)
                resolved_tags.append(new_tag.name)
                self.tag_dict.increment_usage(new_tag.name)

        # --- Step 3: 按tag检索同类实体 ---
        same_tag_entities = []
        try:
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            for node in all_nodes:
                node_tags = set(node.tags or [])
                if node_tags & set(resolved_tags):  # 有交集
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

        # --- Step 4: LLM一次性判断 ---
        if not same_tag_entities:
            # 没有同类实体，直接create
            return {
                "action": "create",
                "final_name": name,
                "resolved_tags": resolved_tags,
                "existing_id": None,
                "aliases_to_add": [],
                "summary_update": None,
                "properties_update": {},
                "new_relations": [],
                "reason": "no existing entities with matching tags",
            }

        # Build LLM prompt
        existing_list = "\n".join(
            f"- {e['name']} (id={e['id'][:8]}, tags={e['tags']}, "
            f"zone={e['zone']}, summary={e['summary'][:80]}, "
            f"aliases={e.get('aliases', [])})"
            for e in same_tag_entities[:15]  # Cap at 15 to avoid token bloat
        )

        tag_taxonomy = ", ".join(
            t.name for t in self.tag_dict.get_all_active()
        )

        user_prompt = (
            f"New entity to resolve:\n"
            f"  name: \"{name}\"\n"
            f"  preliminary tags: {raw_tags}\n"
            f"  zone: {raw_entity.get('zone', 'semantic')}\n"
            f"  summary: {raw_entity.get('summary', '')}\n\n"
            f"Existing entities with similar tags:\n{existing_list}\n\n"
            f"Available tag taxonomy: [{tag_taxonomy}]\n\n"
            f"Decide: merge into existing, update existing, or create new?"
        )

        try:
            result = await call_llm_json(_RESOLVE_ENTITY_SYSTEM, user_prompt, temperature=0.1)
        except Exception as e:
            logger.warning("Entity resolution LLM failed for '%s': %s", name, e)
            return {
                "action": "create",
                "final_name": name,
                "resolved_tags": resolved_tags,
                "existing_id": None,
                "aliases_to_add": [],
                "summary_update": None,
                "properties_update": {},
                "new_relations": [],
                "reason": f"LLM resolution failed: {e}",
            }

        action = result.get("action", "create")
        target_name = result.get("target_entity_name")
        llm_tags = result.get("resolved_tags", resolved_tags)

        # Standardize LLM-returned tags through tag_dict
        final_tags = []
        for t in llm_tags:
            similar = await self.tag_dict.find_similar(t)
            if similar and similar.status == "active":
                final_tags.append(similar.name)
            else:
                new_tag = self.tag_dict.add_tag(t)
                final_tags.append(new_tag.name)

        # Find existing_id if merging/updating
        existing_id = None
        final_name = name
        if action in ("merge", "update") and target_name:
            for e in same_tag_entities:
                if e["name"] == target_name:
                    existing_id = e["id"]
                    final_name = target_name  # Use the existing entity's name
                    break
            if not existing_id:
                # Target not found, fall back to create
                action = "create"
                final_name = name

        return {
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
