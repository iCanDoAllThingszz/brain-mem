"""
WorkingMemory engine component for the brain-memory service.
Session-level background context cache — the working memory of the agent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from server.engine.llm_client import call_llm
from server.storage.buffer import EncoderBuffer
from server.storage.graph import GraphStore
from server.storage.user_profile import UserProfileStore

logger = logging.getLogger(__name__)

_ASSEMBLE_SYSTEM = """\
You are a context assembler for an AI agent's working memory. \
Given structured data about a user, synthesize it into a concise, \
natural-language background context (3-5 sentences) for the agent.

Include these dimensions when data is available:
1. Who the user is and their current situation
2. Active goals and their progress status
3. What was discussed in the last session (if available)
4. Current emotional state and any notable mood shifts
5. Pending items or reminders that need attention
6. Recent key decisions or events (last 7 days)

Rules:
- Be specific, not generic. Include names, dates, numbers when available.
- Prioritize actionable context over background facts.
- If a goal is stalled or overdue, highlight it.
- MUST output in Chinese (中文). Do not output in English.
- Do NOT include thinking process or meta-commentary.
- Do NOT include information that was not provided in the input data.
"""


class WorkingMemory:
    """
    Session-level working memory — the agent's short-term context cache.

    Loaded once at session start (cold boot) from long-term memory,
    then updated incrementally as the conversation progresses.
    Destroyed when the session ends.
    """

    # Class-level in-memory cache: session_id → context dict
    _cache: Dict[str, Dict[str, Any]] = {}

    def __init__(
        self,
        graph: GraphStore,
        buffer: EncoderBuffer,
        profile_store: Optional[UserProfileStore] = None,
    ) -> None:
        self.graph = graph
        self.buffer = buffer
        self.profile_store = profile_store

    async def load(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        user_profile: Optional[Dict[str, Any]] = None,
        agent_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        为新会话冷启动加载工作记忆。

        从长期记忆中提取：
        1. 用户核心档案（如果提供则使用传入的user_profile）
        2. 活跃目标（标记为"计划"或"目标"且status=active的图谱节点）
        3. 近期关键事件（最近7天的情景节点，按重要性取前5个）
        4. 情绪基线（从近期节点的emotional_tag统计）
        5. 上次会话摘要（从缓冲区获取）
        6. 待处理提醒（标记为"计划"/"提醒"且status=pending的节点）

        然后使用LLM合成为自然语言上下文字符串。

        Args:
            tenant_id: 租户标识符
            user_id: 用户标识符
            session_id: 新会话标识符
            user_profile: 可选的预加载用户档案字典
            agent_context: 可选的额外代理上下文字典

        Returns:
            工作记忆字典，包含以下键：
                - "context": str — 自然语言背景上下文
                - "pending_reminders": list[str]
                - "user_goals": list[str]
                - "emotional_baseline": "positive" | "negative" | "neutral"
                - "raw": dict — 供其他引擎组件使用的原始数据
        """
        raw: Dict[str, Any] = {}

        # 1. 用户档案 — 优先使用持久化存储（由LLM逐步丰富），
        #    回退到调用方传入的值
        if self.profile_store:
            stored = self.profile_store.get(tenant_id, user_id)
            raw["user_profile"] = stored["profile"] or user_profile or {}
            stored_goals = stored["goals"]  # 下面可能会用到
        else:
            raw["user_profile"] = user_profile or {}
            stored_goals = []

        # 2. 活跃目标 — 使用存储的目标（LLM丰富的，包含status+progress）
        #    如果可用；否则回退到图谱查询
        # 一次性获取所有活跃节点，供目标、提醒和复习使用（性能优化）
        all_active_nodes = []
        try:
            all_active_nodes = await self.graph.find_active_nodes(tenant_id, user_id)
        except Exception as e:
            logger.warning("find_active_nodes failed: %s", e)

        if stored_goals:
            active_goals = stored_goals
        else:
            active_goals = self._filter_goals(all_active_nodes)
        raw["active_goals"] = active_goals

        # 3. 近期关键事件（最近7天的情景节点）
        recent_events = await self._fetch_recent_events(tenant_id, user_id, days=7, top_n=5)
        raw["recent_events"] = recent_events

        # 4. 情绪基线
        emotional_baseline = self._compute_emotional_baseline(recent_events)
        raw["emotional_baseline"] = emotional_baseline

        # 5. 上次会话摘要
        last_summary = None
        try:
            last_summary = self.buffer.get_latest_session_summary(tenant_id, user_id)
        except Exception as e:
            logger.warning("get_latest_session_summary failed: %s", e)
        raw["last_session_summary"] = last_summary

        # 6. 待处理提醒（复用all_active_nodes）
        pending_reminders = self._filter_pending_reminders(all_active_nodes)
        raw["pending_reminders"] = pending_reminders

        # 7. 待复习记忆（复用all_active_nodes）
        pending_reviews = self._filter_pending_reviews(all_active_nodes)
        raw["pending_reviews"] = pending_reviews

        if agent_context:
            raw["agent_context"] = agent_context

        # 通过LLM合成自然语言上下文
        context_text = await self._synthesize_context(raw)

        wm = {
            "context": context_text,
            "pending_reminders": [r.get("name", str(r)) for r in pending_reminders],
            "pending_reviews": [r.get("name", str(r)) for r in pending_reviews],
            # 对于存储的目标，包含进度信息，让感知器获得更丰富的上下文
            "user_goals": [_goal_label(g) for g in active_goals],
            "emotional_baseline": emotional_baseline,
            "raw": raw,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "loaded_at": datetime.utcnow().isoformat(),
        }

        self._cache[session_id] = wm
        logger.info("Loaded working memory for session %s", session_id)
        return wm

    def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the working memory for an active session.

        Args:
            session_id: Session identifier.

        Returns:
            Working memory dict, or None if not loaded.
        """
        return self._cache.get(session_id)

    def update(self, session_id: str, updates: Dict[str, Any]) -> None:
        """
        Incrementally update working memory during a conversation.

        Merges the updates dict into the existing working memory.
        If the session is not loaded, the update is silently ignored.

        Args:
            session_id: Session identifier.
            updates: Dict of fields to update/add.
        """
        if session_id not in self._cache:
            logger.warning("update called for unknown session %s", session_id)
            return
        # Deep merge "raw" to avoid overwriting sibling keys (e.g. recent_events)
        # when updates only contains a subset like {"raw": {"user_profile": ...}}
        raw_updates = updates.pop("raw", None)
        self._cache[session_id].update(updates)
        if isinstance(raw_updates, dict):
            self._cache[session_id].setdefault("raw", {}).update(raw_updates)

    def destroy(self, session_id: str) -> None:
        """
        Destroy the working memory for a completed session.

        Args:
            session_id: Session identifier to evict from cache.
        """
        if session_id in self._cache:
            del self._cache[session_id]
            logger.info("Destroyed working memory for session %s", session_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_active_goals(
        self, tenant_id: str, user_id: str
    ) -> List[Dict[str, Any]]:
        """Fetch nodes tagged '计划' or '目标' with status=active."""
        try:
            nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            return self._filter_goals(nodes)
        except Exception as e:
            logger.warning("fetch_active_goals failed: %s", e)
            return []

    @staticmethod
    def _filter_goals(nodes: List) -> List[Dict[str, Any]]:
        """Filter goal nodes from a pre-fetched list of active nodes."""
        goals = []
        target_tags = {"计划", "目标"}
        for node in nodes:
            node_tags = set(node.tags or [])
            if node_tags & target_tags and node.status == "active":
                goals.append({
                    "id": node.id,
                    "name": node.name,
                    "summary": node.summary,
                    "tags": node.tags,
                })
        # Deduplicate by id
        seen = set()
        deduped = []
        for g in goals:
            if g["id"] not in seen:
                seen.add(g["id"])
                deduped.append(g)
        return deduped[:10]

    async def _fetch_recent_events(
        self, tenant_id: str, user_id: str, days: int = 7, top_n: int = 5
    ) -> List[Dict[str, Any]]:
        """Fetch recent episodic nodes from the last N days, sorted by importance."""
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        events = []
        try:
            nodes = await self.graph.find_active_nodes(tenant_id, user_id, zone="episodic")
            for node in nodes:
                created = getattr(node, "created_at", None)
                if created:
                    created_str = created.isoformat() if isinstance(created, datetime) else str(created)
                    if created_str >= cutoff:
                        events.append({
                            "id": node.id,
                            "name": node.name,
                            "summary": node.summary,
                            "importance": node.importance,
                            "emotional_tag": node.emotional_tag,
                            "created_at": created_str,
                        })
        except Exception as e:
            logger.warning("fetch_recent_events failed: %s", e)

        events.sort(key=lambda x: x.get("importance", 0), reverse=True)
        return events[:top_n]

    async def _fetch_pending_reminders(
        self, tenant_id: str, user_id: str
    ) -> List[Dict[str, Any]]:
        """Fetch nodes tagged '计划' or '提醒' with properties.status=pending."""
        try:
            nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            return self._filter_pending_reminders(nodes)
        except Exception as e:
            logger.warning("fetch_pending_reminders failed: %s", e)
            return []

    @staticmethod
    def _filter_pending_reminders(nodes: List) -> List[Dict[str, Any]]:
        """Filter pending reminder nodes from a pre-fetched list."""
        reminders = []
        for node in nodes:
            tags = node.tags or []
            props = node.properties or {}
            if any(t in tags for t in ["计划", "提醒"]) and props.get("status") == "pending":
                reminders.append({
                    "id": node.id,
                    "name": node.name,
                    "summary": node.summary,
                    "tags": tags,
                })
        return reminders[:10]

    async def _fetch_pending_reviews(
        self, tenant_id: str, user_id: str
    ) -> List[Dict[str, Any]]:
        """Fetch nodes with properties.needs_review=true (spaced repetition)."""
        try:
            nodes = await self.graph.find_active_nodes(tenant_id, user_id)
            return self._filter_pending_reviews(nodes)
        except Exception as e:
            logger.warning("fetch_pending_reviews failed: %s", e)
            return []

    @staticmethod
    def _filter_pending_reviews(nodes: List) -> List[Dict[str, Any]]:
        """Filter review-pending nodes from a pre-fetched list."""
        reviews = []
        for node in nodes:
            props = node.properties or {}
            if props.get("needs_review"):
                reviews.append({
                    "id": node.id,
                    "name": node.name,
                    "summary": node.summary,
                    "importance": node.importance,
                    "retrieval_strength": node.retrieval_strength,
                    "review_count": props.get("review_count", 0),
                })
        return reviews[:10]

    @staticmethod
    def _compute_emotional_baseline(
        recent_events: List[Dict[str, Any]],
    ) -> str:
        """
        Compute emotional baseline from recent events' emotional tags.

        Returns "positive", "negative", or "neutral".
        """
        if not recent_events:
            return "neutral"

        positive_types = {"joy", "surprise"}
        negative_types = {"sadness", "anger", "fear"}
        pos_count = 0
        neg_count = 0

        for event in recent_events:
            et = event.get("emotional_tag", {})
            if isinstance(et, dict):
                etype = et.get("type", "neutral")
                intensity = float(et.get("intensity", 0))
                if intensity >= 3:
                    if etype in positive_types:
                        pos_count += 1
                    elif etype in negative_types:
                        neg_count += 1

        if pos_count > neg_count:
            return "positive"
        elif neg_count > pos_count:
            return "negative"
        return "neutral"

    async def _synthesize_context(self, raw: Dict[str, Any]) -> str:
        """Use LLM to synthesize raw data into a natural language context string."""
        # Build a structured text summary for the LLM
        parts = []

        profile = raw.get("user_profile", {})
        if profile:
            parts.append(f"User profile: {profile}")

        goals = raw.get("active_goals", [])
        if goals:
            goal_names = ", ".join(g.get("name", "") for g in goals)
            parts.append(f"Active goals: {goal_names}")

        events = raw.get("recent_events", [])
        if events:
            event_summaries = "; ".join(
                e.get("summary") or e.get("name", "") for e in events
            )
            parts.append(f"Recent events (last 7 days): {event_summaries}")

        baseline = raw.get("emotional_baseline", "neutral")
        parts.append(f"Emotional baseline: {baseline}")

        last_summary = raw.get("last_session_summary")
        if last_summary:
            summary_text = last_summary.get("summary_text", "")
            if summary_text:
                parts.append(f"Last session summary: {summary_text}")
            topics = last_summary.get("topics", [])
            if topics:
                parts.append(f"Last session topics: {', '.join(topics)}")
            pending = last_summary.get("pending_points", [])
            if pending:
                parts.append(f"Pending from last session: {', '.join(pending)}")

        reminders = raw.get("pending_reminders", [])
        if reminders:
            reminder_names = ", ".join(r.get("name", "") for r in reminders)
            parts.append(f"Pending reminders: {reminder_names}")

        reviews = raw.get("pending_reviews", [])
        if reviews:
            review_names = ", ".join(r.get("name", "") for r in reviews)
            parts.append(f"Memories needing review (spaced repetition): {review_names}")

        if not parts:
            return "No prior context available for this user."

        user_prompt = "Structured data:\n" + "\n".join(parts)
        try:
            return await call_llm(_ASSEMBLE_SYSTEM, user_prompt, temperature=0.3)
        except Exception as e:
            logger.error("Context synthesis failed: %s", e)
            return "\n".join(parts)


def _goal_label(goal: Any) -> str:
    """Format a goal dict into a short label for prompt injection.

    Works for both graph-style goals ({"name", "summary", ...}) and
    profile-store goals ({"name", "status", "progress"}).
    """
    if not isinstance(goal, dict):
        return str(goal)
    name = goal.get("name", "")
    progress = goal.get("progress", "")
    status = goal.get("status", "active")
    label = name
    if progress:
        label += f"（{progress}）"
    if status and status != "active":
        label += f"[{status}]"
    return label
