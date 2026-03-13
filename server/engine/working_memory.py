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
- Write in the same language as the input data.
- Do NOT include thinking process or meta-commentary.
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

    def __init__(self, graph: GraphStore, buffer: EncoderBuffer) -> None:
        """
        Initialize working memory.

        Args:
            graph: GraphStore instance for long-term memory queries.
            buffer: EncoderBuffer instance for recent session summaries.
        """
        self.graph = graph
        self.buffer = buffer

    async def load(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        user_profile: Optional[Dict[str, Any]] = None,
        agent_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Cold-boot load of working memory for a new session.

        Pulls from long-term memory:
        1. User core profile (uses passed-in user_profile if provided).
        2. Active goals (graph nodes tagged "计划" or "目标" with status=active).
        3. Recent key events (last 7 days episodic nodes, top 5 by importance).
        4. Emotional baseline (statistics from recent nodes' emotional_tag).
        5. Last session summary (from buffer).
        6. Pending reminders (nodes tagged "计划"/"提醒" with status=pending).

        Then uses LLM to synthesize into a natural-language context string.

        Args:
            tenant_id: Tenant identifier.
            user_id: User identifier.
            session_id: New session identifier.
            user_profile: Optional pre-loaded user profile dict.
            agent_context: Optional additional agent context dict.

        Returns:
            Working memory dict with keys:
                - "context": str — natural language background context
                - "pending_reminders": list[str]
                - "user_goals": list[str]
                - "emotional_baseline": "positive" | "negative" | "neutral"
                - "raw": dict — raw data for other engine components
        """
        raw: Dict[str, Any] = {}

        # 1. User profile
        raw["user_profile"] = user_profile or {}

        # 2. Active goals
        active_goals = await self._fetch_active_goals(tenant_id, user_id)
        raw["active_goals"] = active_goals

        # 3. Recent key events (last 7 days episodic nodes)
        recent_events = await self._fetch_recent_events(tenant_id, user_id, days=7, top_n=5)
        raw["recent_events"] = recent_events

        # 4. Emotional baseline
        emotional_baseline = self._compute_emotional_baseline(recent_events)
        raw["emotional_baseline"] = emotional_baseline

        # 5. Last session summary
        last_summary = None
        try:
            last_summary = self.buffer.get_latest_session_summary(tenant_id, user_id)
        except Exception as e:
            logger.warning("get_latest_session_summary failed: %s", e)
        raw["last_session_summary"] = last_summary

        # 6. Pending reminders
        pending_reminders = await self._fetch_pending_reminders(tenant_id, user_id)
        raw["pending_reminders"] = pending_reminders

        if agent_context:
            raw["agent_context"] = agent_context

        # Synthesize natural language context via LLM
        context_text = await self._synthesize_context(raw)

        wm = {
            "context": context_text,
            "pending_reminders": [r.get("name", str(r)) for r in pending_reminders],
            "user_goals": [g.get("name", str(g)) for g in active_goals],
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
        self._cache[session_id].update(updates)
        # Also merge into raw if provided
        if "raw" in updates and isinstance(updates["raw"], dict):
            self._cache[session_id].setdefault("raw", {}).update(updates["raw"])

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
        goals = []
        for tag in ["计划", "目标"]:
            try:
                nodes = await self.graph.find_active_nodes(tenant_id, user_id)
                for node in nodes:
                    if tag in (node.tags or []) and node.status == "active":
                        goals.append({
                            "id": node.id,
                            "name": node.name,
                            "summary": node.summary,
                            "tags": node.tags,
                        })
            except Exception as e:
                logger.warning("fetch_active_goals (tag=%s) failed: %s", tag, e)
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
        reminders = []
        try:
            nodes = await self.graph.find_active_nodes(tenant_id, user_id)
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
        except Exception as e:
            logger.warning("fetch_pending_reminders failed: %s", e)
        return reminders[:10]

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

        if not parts:
            return "No prior context available for this user."

        user_prompt = "Structured data:\n" + "\n".join(parts)
        try:
            return await call_llm(_ASSEMBLE_SYSTEM, user_prompt, temperature=0.3)
        except Exception as e:
            logger.error("Context synthesis failed: %s", e)
            return "\n".join(parts)
