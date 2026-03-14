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
from server.engine.log_writer import LogWriter
from server.models.node import Node
from server.storage.buffer import EncoderBuffer
from server.storage.graph import GraphStore
from server.storage.tag_dict import TagDict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Step 1: 粗提取 — 从消息中提取原始实体和关系
# ---------------------------------------------------------------------------
_EXTRACT_SYSTEM = """\
You are an information extraction engine for a PERSONAL memory system. \
Extract entities and relationships that are specific to this user's life.

Rules:
- Extract named entities: people, organizations, places, concepts, events, decisions, plans.
- ONLY extract entities that are relevant to the user personally. \
  Skip universal common knowledge (e.g., "地球", "太阳", "水") unless the user \
  has a personal connection to it.
- **PRONOUN RESOLUTION**: Replace pronouns like "我", "用户", "本人" with the user's actual name \
  from context (e.g., "赵禹"). Never create an entity named "用户" or "我" — always resolve to \
  the real person. If the user's name is unknown, use "用户本人" as a placeholder.
- Assign a memory zone: semantic / episodic / procedural / emotional.
- Assign 1-2 preliminary tags per entity (Chinese labels preferred).
- Ignore garbled/encoded names (like "Gbusrw Jflvnkmwi") — display artifacts.
- Relation types: UPPER_SNAKE_CASE (e.g., WORKS_AT, DECIDED_TO).
- If the message mixes common knowledge with personal info, only extract the personal parts.

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
1. "merge" — The new entity is the SAME entity as an existing one (same person/org/concept). \
   Use this when the new entity is just another mention or alias of an existing entity. \
   Example: "腾讯" and "Tencent" are the same company → merge.
2. "update" — The new entity adds NEW information to an existing entity. \
   Use this when the entity already exists but the new mention provides additional details. \
   Example: existing "赵禹" has no job info, new mention says "赵禹在美团工作" → update.
3. "create" — The new entity is genuinely NEW and distinct from all existing entities. \
   Only use this if you're confident it's a different entity.

**IMPORTANT**: Be conservative with "create". If there's ANY chance the entity already exists, \
prefer "merge" or "update". Duplicate entities are worse than merged entities.

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
        elif category.startswith("log_"):
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

        # Step 0: Semantic dedup check against recent buffer (hybrid approach)
        recent = self.buffer.read_recent(tenant_id, user_id, limit=20)
        if await self._is_semantic_duplicate(message, recent):
            logger.info("Skipping semantically duplicate message: %.60s", message)
            return {"skipped": True, "reason": "semantic_duplicate"}

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
        target_entity = evaluation.get("target_entity")

        # Write log to file and update graph
        result = await self.log_writer.write_log(
            category=category,
            message=message,
            target_entity=target_entity,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # Also write a summary record to buffer so retriever can find it
        # Buffer stores the rewrite (high-density), not raw details
        file_path = result.get("file_path", "")
        summary_for_buffer = message
        if target_entity:
            summary_for_buffer = f"[{target_entity}] {message} (详见: {file_path})"

        buffer_unit = {
            "id": str(__import__('uuid').uuid4()),
            "type": "log_index",
            "message": summary_for_buffer,
            "category": category,
            "target_entity": target_entity,
            "file_path": file_path,
            "entities": [],
            "relations": [],
            "importance": self._compute_importance(evaluation),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.buffer.write(tenant_id, user_id, session_id, buffer_unit)

        logger.info(
            "Encoded log entry (category=%s, target=%s, file=%s, buffer=yes)",
            category, target_entity, file_path
        )

        return {
            "type": "log",
            "category": category,
            "target_entity": target_entity,
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
        target_entity = evaluation.get("target_entity")
        correction_type = evaluation.get("correction_type", "correct")

        if not target_entity:
            logger.warning("Reconsolidation missing target_entity, skipping")
            return {"skipped": True, "reason": "missing_target_entity"}

        # Step 1: Find the target node(s) by name or fuzzy match
        nodes = await self.graph.find_nodes_by_name(target_entity, tenant_id, user_id)
        if not nodes:
            # Try fuzzy search
            nodes = await self.graph.find_nodes_fuzzy(target_entity, tenant_id, user_id)

        if not nodes:
            # Auto-create the target entity if it doesn't exist
            # (reconsolidation implies the user believes this entity should exist)
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
            # Factual correction: update summary/content
            old_values["summary"] = node.summary
            old_values["content"] = node.content
            updates["summary"] = message
            updates["content"] = message

        elif correction_type == "supplement":
            # Supplement: append to existing content
            old_values["content"] = node.content
            new_content = f"{node.content}\n{message}" if node.content else message
            updates["content"] = new_content
            # Also update summary to reflect the supplement
            updates["summary"] = f"{node.summary} | {message[:50]}" if node.summary else message[:50]

        elif correction_type == "reframe":
            # Emotional reframe: update emotional_tag
            old_values["emotional_tag"] = node.emotional_tag
            # Use LLM to extract new emotional tag from message
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

        # Limit history to last 10 corrections
        if len(correction_history) > 10:
            correction_history = correction_history[-10:]

        updates["properties"] = {
            **node.properties,
            "_correction_history": correction_history,
        }

        # Step 4: Increment version
        updates["version"] = node.version + 1

        # Step 5: Update the node
        await self.graph.update_node(node_id, updates)

        logger.info(
            "Reconsolidation: updated node %s (entity=%s, type=%s, version=%d→%d)",
            node_id[:8], target_entity, correction_type, node.version, node.version + 1
        )

        return {
            "type": "reconsolidation",
            "node_id": node_id,
            "target_entity": target_entity,
            "correction_type": correction_type,
            "nodes_updated": 1,
            "old_version": node.version,
            "new_version": node.version + 1,
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

        if not trigger_type or not trigger_value or not action:
            logger.warning("Prospective memory missing required fields, skipping")
            return {"skipped": True, "reason": "missing_required_fields"}

        # Create a memory node for the prospective memory
        node_id = str(uuid.uuid4())
        node = Node(
            id=node_id,
            name=f"提醒: {action[:30]}",
            tags=["计划", "提醒"],
            zone="procedural",
            summary=f"{trigger_type}触发器: {action}",
            content=message,
            importance=8.0,  # High importance for reminders
            properties={
                "trigger_type": trigger_type,
                "trigger_value": trigger_value,
                "action": action,
                "status": "pending",
                "created_from": message,
                "session_id": session_id,
            },
        )

        # Write directly to graph (bypass buffer/consolidation for immediate availability)
        await self.graph.create_node(node, tenant_id, user_id)

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
            "entities": [],
            "relations": [],
            "importance": 8.0,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.buffer.write(tenant_id, user_id, session_id, buffer_unit)

        logger.info(
            "Encoded prospective memory (type=%s, trigger=%s, action=%s, node=%s)",
            trigger_type, trigger_value, action, node_id[:8]
        )

        return {
            "type": "prospective",
            "node_id": node_id,
            "trigger_type": trigger_type,
            "trigger_value": trigger_value,
            "action": action,
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
        target_entity = evaluation.get("target_entity")

        if not target_entity:
            logger.warning("Forget missing target_entity, skipping")
            return {"skipped": True, "reason": "missing_target_entity"}

        # Step 1: Find the target node(s) by name or fuzzy match
        nodes = await self.graph.find_nodes_by_name(target_entity, tenant_id, user_id)
        if not nodes:
            # Try fuzzy search
            nodes = await self.graph.find_nodes_fuzzy(target_entity, tenant_id, user_id)

        if not nodes:
            logger.warning("Target entity '%s' not found for forgetting", target_entity)
            return {"skipped": True, "reason": "target_entity_not_found", "target_entity": target_entity}

        # Step 2: Suppress all matching nodes
        suppressed_count = 0
        suppressed_ids = []

        for node in nodes:
            node_id = node.id
            try:
                # Update node status to suppressed
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
                suppressed_count += 1
                suppressed_ids.append(node_id)

                logger.info(
                    "Suppressed node %s (entity=%s) via forget command",
                    node_id[:8], node.name
                )
            except Exception as e:
                logger.warning("Failed to suppress node %s: %s", node_id, e)

        if suppressed_count == 0:
            return {"skipped": True, "reason": "suppression_failed", "target_entity": target_entity}

        logger.info(
            "Forget: suppressed %d nodes (entity=%s)",
            suppressed_count, target_entity
        )

        return {
            "type": "forget",
            "target_entity": target_entity,
            "nodes_suppressed": suppressed_count,
            "suppressed_ids": suppressed_ids,
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
    # Step 0: Semantic deduplication
    # ------------------------------------------------------------------

    async def _is_semantic_duplicate(
        self,
        message: str,
        recent_units: List[Dict[str, Any]],
    ) -> bool:
        """
        Hybrid semantic deduplication:
        1. Quick keyword overlap filter (70%+ overlap → likely duplicate)
        2. For borderline cases (40-70%), use LLM to judge
        """
        if not recent_units:
            return False

        msg_words = set(self._tokenize_chinese(message))
        if len(msg_words) < 3:
            # Too short to meaningfully compare
            return False

        borderline_candidates = []

        for unit in recent_units:
            existing_msg = unit.get("message", "").strip()
            if not existing_msg:
                continue

            # Exact match
            if existing_msg == message:
                return True

            existing_words = set(self._tokenize_chinese(existing_msg))
            if len(existing_words) < 3:
                continue

            # Keyword overlap ratio
            overlap = len(msg_words & existing_words)
            union = len(msg_words | existing_words)
            ratio = overlap / union if union > 0 else 0

            if ratio >= 0.7:
                # High overlap → definitely duplicate
                logger.debug("High keyword overlap (%.2f) with existing message", ratio)
                return True
            elif 0.4 <= ratio < 0.7:
                # Borderline → need LLM check
                borderline_candidates.append(existing_msg)

        # LLM check for borderline cases
        if borderline_candidates:
            return await self._llm_similarity_check(message, borderline_candidates[:3])

        return False

    @staticmethod
    def _tokenize_chinese(text: str) -> List[str]:
        """Simple Chinese tokenization: split by whitespace + punctuation, keep CJK chars."""
        import re
        # Remove punctuation, split by whitespace
        tokens = re.findall(r'[\w]+', text.lower())
        return [t for t in tokens if len(t) > 1]  # Filter single chars

    async def _llm_similarity_check(
        self,
        new_message: str,
        existing_messages: List[str],
    ) -> bool:
        """Use LLM to judge if new_message is semantically duplicate of any existing message."""
        existing_list = "\n".join(f"{i+1}. {msg}" for i, msg in enumerate(existing_messages))
        system_prompt = """\
You are a semantic similarity judge. Determine if the new message is semantically \
duplicate (same core meaning) as any of the existing messages.

Return ONLY valid JSON:
{
  "is_duplicate": true|false,
  "reason": "one-sentence explanation"
}
"""
        user_prompt = (
            f"New message:\n\"{new_message}\"\n\n"
            f"Existing messages:\n{existing_list}\n\n"
            f"Is the new message a semantic duplicate of any existing message?"
        )

        try:
            result = await call_llm_json(system_prompt, user_prompt, temperature=0.1)
            return bool(result.get("is_duplicate", False))
        except Exception as e:
            logger.warning("LLM similarity check failed: %s", e)
            return False  # Fail-open: allow encoding if LLM fails

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
        4. 干扰检测：检查是否存在高度相似的旧实体，标记冲突或更新关系
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

        # --- Step 3: 按tag检索同类实体 + 按名称模糊匹配 ---
        same_tag_entities = []
        try:
            all_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            for node in all_nodes:
                node_tags = set(node.tags or [])
                node_name_lower = node.name.lower()
                name_lower = name.lower()

                # Match by tag overlap OR name similarity
                has_tag_overlap = bool(node_tags & set(resolved_tags))
                has_name_similarity = (
                    name_lower in node_name_lower or
                    node_name_lower in name_lower or
                    name_lower == node_name_lower
                )

                if has_tag_overlap or has_name_similarity:
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

        # --- Step 5: Interference detection ---
        # Check if this is an update that interferes with old information
        if action == "update" and existing_id:
            interference_result = await self._check_interference(
                existing_id, raw_entity, resolution_result, tenant_id, user_id
            )
            # Merge interference results into resolution
            if interference_result:
                resolution_result["properties_update"] = {
                    **resolution_result.get("properties_update", {}),
                    **interference_result.get("properties_update", {}),
                }
                resolution_result["relations_to_invalidate"] = interference_result.get("relations_to_invalidate", [])

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
