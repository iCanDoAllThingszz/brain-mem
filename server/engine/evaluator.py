"""
Evaluator engine component for the brain-memory service.
Corresponds to the prefrontal cortex + amygdala in the human brain.
Performs deep evaluation of a message's memory value before encoding.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from server.engine.llm_client import call_llm_json

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a memory value evaluator for an AI agent's long-term memory system. \
Your task is to assess how worthy a message is of being stored in long-term memory.

Evaluate the message on three dimensions (0-10 integer scores). \
Use the FULL 0-10 range — do NOT cluster scores around 3-5.

Scoring anchors:

1. task_relevance (0-10):
   0-2: Completely unrelated to any known goal (e.g., random chat, weather small talk)
   3-4: Tangentially related (e.g., mentions a topic the user works with)
   5-6: Moderately relevant (e.g., progress update on an active project)
   7-8: Directly advances a key goal (e.g., "I got an interview at ByteDance")
   9-10: Critical life decision or milestone (e.g., "I decided to resign", "I got the offer")

2. emotional_intensity (0-10):
   0-2: Neutral, matter-of-fact
   3-4: Mild emotion (slight frustration, mild happiness)
   5-6: Moderate emotion (clearly happy, noticeably stressed)
   7-8: Strong emotion (very excited, very angry, crying)
   9-10: Extreme emotion (life-changing joy, deep grief, panic)
   emotion_type must be one of: joy, sadness, anger, fear, surprise, neutral

3. novelty (0-10):
   0-2: Already well-known information, repeated fact
   3-4: Minor new detail about a known topic
   5-6: Meaningful new information
   7-8: Surprising new fact or unexpected development
   9-10: Completely unexpected, paradigm-shifting information

Encoding decision rules (apply in order):
- If task_relevance >= 7 → encode_decision = true, encode_priority = "high"
- If emotional_intensity >= 7 → encode_decision = true, encode_priority = "high"
- If novelty >= 8 → encode_decision = true, encode_priority = "medium"
- If task_relevance >= 5 OR novelty >= 5 → encode_decision = true, encode_priority = "low"
- Otherwise → encode_decision = false, encode_priority = "low"

Return ONLY valid JSON in this exact format:
{
  "task_relevance": <0-10>,
  "emotional_intensity": <0-10>,
  "emotion_type": "joy|sadness|anger|fear|surprise|neutral",
  "novelty": <0-10>,
  "encode_decision": true|false,
  "encode_priority": "high|medium|low",
  "reason": "one-sentence explanation"
}
"""


class Evaluator:
    """
    Deep memory value evaluator — the prefrontal cortex of the memory system.

    Scores a message on task relevance, emotional intensity, and novelty,
    then decides whether and at what priority to encode it into long-term memory.
    """

    async def evaluate(
        self,
        message: str,
        working_memory: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate the memory value of a message.

        Args:
            message: The message text to evaluate.
            working_memory: Optional session working memory. When provided,
                the user's goals and recent focus areas are injected to improve
                task_relevance scoring.

        Returns:
            Dict with keys:
                - "task_relevance": int 0-10
                - "emotional_intensity": int 0-10
                - "emotion_type": str
                - "novelty": int 0-10
                - "encode_decision": bool
                - "encode_priority": "high" | "medium" | "low"
                - "reason": str
        """
        user_prompt = self._build_prompt(message, working_memory)
        try:
            result = await call_llm_json(_SYSTEM_PROMPT, user_prompt)
            return self._validate(result)
        except Exception as e:
            logger.error("Evaluator.evaluate failed: %s", e)
            # Fail-safe: return a low-priority encode decision
            return {
                "task_relevance": 5,
                "emotional_intensity": 0,
                "emotion_type": "neutral",
                "novelty": 5,
                "encode_decision": True,
                "encode_priority": "low",
                "reason": f"evaluation error, defaulting to encode: {e}",
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(message: str, working_memory: Optional[Dict[str, Any]]) -> str:
        """Build the evaluation prompt with optional working memory context."""
        parts = [f'Message to evaluate:\n"""\n{message}\n"""']

        if working_memory:
            context_parts = []
            if working_memory.get("user_goals"):
                goals = "\n".join(f"- {g}" for g in working_memory["user_goals"])
                context_parts.append(f"User's active goals:\n{goals}")
            raw = working_memory.get("raw", {})
            if raw.get("recent_events"):
                events_text = "; ".join(
                    str(e.get("summary", e.get("name", "")))
                    for e in raw["recent_events"][:5]
                )
                context_parts.append(f"Recent key events: {events_text}")
            # Inject user profile for better context
            profile = raw.get("user_profile", {})
            if profile:
                context_parts.append(f"User profile: {profile}")
            if context_parts:
                parts.append("Context for task_relevance scoring:\n" + "\n".join(context_parts))

        return "\n\n".join(parts)

    @staticmethod
    def _validate(result: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalise the LLM evaluation result."""
        valid_emotions = {"joy", "sadness", "anger", "fear", "surprise", "neutral"}
        valid_priorities = {"high", "medium", "low"}

        def clamp_int(val: Any, default: int = 5) -> int:
            try:
                return max(0, min(10, int(val)))
            except (TypeError, ValueError):
                return default

        task_relevance = clamp_int(result.get("task_relevance", 5))
        emotional_intensity = clamp_int(result.get("emotional_intensity", 0))
        novelty = clamp_int(result.get("novelty", 5))

        emotion_type = result.get("emotion_type", "neutral")
        if emotion_type not in valid_emotions:
            emotion_type = "neutral"

        encode_priority = result.get("encode_priority", "low")
        if encode_priority not in valid_priorities:
            encode_priority = "low"

        # Re-apply encoding rules to ensure consistency
        encode_decision = bool(result.get("encode_decision", False))
        if task_relevance >= 7 or emotional_intensity >= 7 or novelty >= 8:
            encode_decision = True
            if task_relevance >= 7 or emotional_intensity >= 7:
                encode_priority = "high"
        elif task_relevance >= 5 or novelty >= 5:
            encode_decision = True
            if encode_priority == "high":
                pass  # keep high if LLM said so
            else:
                encode_priority = "low"

        return {
            "task_relevance": task_relevance,
            "emotional_intensity": emotional_intensity,
            "emotion_type": emotion_type,
            "novelty": novelty,
            "encode_decision": encode_decision,
            "encode_priority": encode_priority,
            "reason": result.get("reason", ""),
        }
