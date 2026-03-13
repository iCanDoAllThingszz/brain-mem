"""
Perceiver engine component for the brain-memory service.
Corresponds to the sensory cortex + thalamus in the human brain.
Rapidly classifies incoming messages to decide if they warrant further processing.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from server.engine.llm_client import call_llm_json

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a message classifier for a memory system. Your job is to quickly categorize \
incoming messages into one of three types.

Classification rules (recall-first — when in doubt, prefer "informative"):
- "noise": Pure social filler with zero information content.
  Examples: "嗯嗯", "好的", "哈哈", "OK", "收到", "😄", "哦"
- "command": A pure instruction or request that asks the agent to DO something.
  Examples: "帮我搜一下X", "查一下天气", "翻译这段话", "设个提醒"
- "informative": Contains new facts, relationships, decisions, plans, opinions, or \
emotional expressions that are worth remembering.
  Examples: "我今天去字节面试了", "我决定辞职", "我最近压力很大", "公司要裁员了"

If a message is BOTH a command AND informative (e.g., "帮我查一下，我明天要去北京出差"), \
classify as "informative".

Return ONLY valid JSON in this exact format:
{
  "type": "noise" | "command" | "informative",
  "reason": "one-sentence explanation"
}
"""


class Perceiver:
    """
    Rapid message classifier — the sensory gateway of the memory system.

    Determines whether a message is worth processing further by classifying it
    as noise, a command, or informative content.
    """

    async def classify(
        self,
        message: str,
        working_memory: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Classify a message into noise / command / informative.

        Args:
            message: The raw message text to classify.
            working_memory: Optional session working memory dict. When provided,
                the user's current goals and context are injected into the prompt
                to improve classification accuracy.

        Returns:
            Dict with keys:
                - "type": "noise" | "command" | "informative"
                - "reason": str — brief explanation of the decision
        """
        user_prompt = self._build_prompt(message, working_memory)
        try:
            result = await call_llm_json(_SYSTEM_PROMPT, user_prompt)
            # Validate and normalise
            msg_type = result.get("type", "informative")
            if msg_type not in {"noise", "command", "informative"}:
                logger.warning("Unexpected classify type '%s', defaulting to informative", msg_type)
                msg_type = "informative"
            return {
                "type": msg_type,
                "reason": result.get("reason", ""),
            }
        except Exception as e:
            logger.error("Perceiver.classify failed: %s", e)
            # Fail-safe: treat as informative so we don't lose data
            return {"type": "informative", "reason": f"classification error: {e}"}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(message: str, working_memory: Optional[Dict[str, Any]]) -> str:
        """Build the user prompt, optionally injecting working memory context."""
        parts = [f'Message to classify:\n"""\n{message}\n"""']

        if working_memory:
            context_parts = []
            if working_memory.get("user_goals"):
                goals = ", ".join(working_memory["user_goals"])
                context_parts.append(f"User's current goals: {goals}")
            if working_memory.get("context"):
                # Truncate to avoid token bloat
                ctx = working_memory["context"][:500]
                context_parts.append(f"Session context: {ctx}")
            if context_parts:
                parts.append("Background context:\n" + "\n".join(context_parts))

        return "\n\n".join(parts)
