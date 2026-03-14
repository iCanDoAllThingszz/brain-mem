"""
Perceiver engine component for the brain-memory service.
Corresponds to the sensory cortex + thalamus in the human brain.

v2: Beyond classification — also rewrites informative messages into
high-density, entity-explicit memory inputs. The same query in different
contexts can carry different meanings, so rewriting uses user profile,
working memory, and long-term context.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from server.engine.llm_client import call_llm_json

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are the sensory gateway (thalamus) of a personal memory system. \
You have TWO jobs:

## Job 1: Classify
Categorize the message into one of three types:

- "noise": Zero personal information content. Includes:
  * Pure social filler: "嗯嗯", "好的", "哈哈", "OK", "收到"
  * Universal common knowledge: "地球是圆的", "天是蓝的", "水是H2O"
  * Generic weather/time remarks with no personal context

- "command": A pure instruction with NO personal information embedded. \
  This includes debugging/troubleshooting queries about temporary technical issues. \
  Examples: "翻译这段话", "查一下天气", "检查一下日志", "为什么会有两个服务"

- "informative": Contains information worth remembering about this user. \
  This includes EXPLICIT info (facts, decisions, plans) AND IMPLICIT info \
  (interests revealed by questions, emotions revealed by tone, intentions \
  revealed by requests).

Key rules:
- Questions reveal interests: "最近AI agent有啥新动向" → user is interested in AI agents
- Commands reveal intentions: "帮我搜上海AI公司" → user is researching AI companies
- Emotions reveal state: "今天好累" → user is fatigued
- Mixed messages: classify as "informative" if ANY personal info exists
- When in doubt → "informative" (recall-first principle)

## Job 2: Rewrite (only when type = "informative")
Rewrite the original message into a HIGH-DENSITY memory statement that:
1. Makes the user (subject) explicit — use their name from context
2. Records FACTS as stated — do NOT generalize single events into habits or preferences
3. Connects to known context (goals, recent events, career plans) when relevant
4. Strips away common knowledge noise, keeping only personal-relevant parts
5. Makes entity relationships explicit
6. **PRESERVE ORIGINAL INTENT** — Do NOT over-infer or change the semantic meaning. \
   If the user is questioning/doubting something, keep that tone. \
   If the user is stating a fact, keep it factual. \
   When uncertain about intent, prefer a more literal rewrite over speculation.
7. **NO OVER-INFERENCE** — A single action does NOT imply a habit or preference. \
   "吃了一个苹果" means they ate an apple ONCE, NOT that they "have a habit of eating fruit". \
   "跑了5公里" means they ran 5km ONCE, NOT that they "regularly exercise". \
   Only state what is explicitly said. Pattern recognition is the consolidator's job, not yours.

Examples:
- Original: "最近ai agent有啥新动向"
  Context: User is 赵禹, planning to switch to AI startup
  Rewrite: "赵禹询问AI Agent最新动态，表明他持续关注AI Agent领域，与跳槽AI创业公司的职业规划相关"

- Original: "帮我搜一下上海AI公司"
  Context: User plans to move to Shanghai
  Rewrite: "赵禹正在调研上海AI公司，这是他跳槽计划的具体行动步骤"

- Original: "今天好累"
  Context: User has been busy with interviews + work
  Rewrite: "赵禹表达疲惫感，可能与近期面试和工作双线压力有关"

- Original: "地球是圆的，对了我打算学Rust"
  Rewrite: "赵禹计划学习Rust语言以拓展技术栈"

- Original: "好的 明天开始记录饮食"
  Context: User has a weight loss plan, stalled for 4 days
  Rewrite: "赵禹承诺明天重新开始记录饮食，减肥计划即将恢复"

- Original: "早上我吃了一个苹果"
  Rewrite: "赵禹早上吃了一个苹果"
  ❌ WRONG: "赵禹有早餐吃水果的习惯" (over-inference from single event)

- Original: "我今天中午吃了一碗牛肉面 大概600大卡"
  Rewrite: "赵禹今日午餐吃了一碗牛肉面，约600大卡"
  ❌ WRONG: "赵禹喜欢吃牛肉面" (over-inference)

- Original: "怎么会有两个服务 不是就一个服务吗"
  Context: User is debugging a memory system project
  Rewrite: "赵禹对系统中存在两个服务表示疑惑，认为应该只有一个服务"

For "noise" or "command" types, rewrite should be null.

Return ONLY valid JSON:
{
  "type": "noise" | "command" | "informative",
  "reason": "one-sentence classification explanation",
  "rewrite": "rewritten high-density memory statement" | null
}
"""


class Perceiver:
    """
    Sensory gateway v2 — classifies AND rewrites messages.

    For informative messages, produces a high-density rewrite that makes
    implicit information explicit, using user context for disambiguation.
    """

    async def classify(
        self,
        message: str,
        working_memory: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Classify and optionally rewrite a message.

        Returns:
            Dict with keys:
                - "type": "noise" | "command" | "informative"
                - "reason": str
                - "rewrite": str | None — high-density rewrite for informative messages
        """
        user_prompt = self._build_prompt(message, working_memory)
        try:
            result = await call_llm_json(_SYSTEM_PROMPT, user_prompt)
            msg_type = result.get("type", "informative")
            if msg_type not in {"noise", "command", "informative"}:
                logger.warning("Unexpected classify type '%s', defaulting to informative", msg_type)
                msg_type = "informative"

            rewrite = result.get("rewrite")
            # Validate rewrite
            if msg_type != "informative":
                rewrite = None
            elif rewrite and len(rewrite.strip()) < 5:
                rewrite = None

            return {
                "type": msg_type,
                "reason": result.get("reason", ""),
                "rewrite": rewrite,
            }
        except Exception as e:
            logger.error("Perceiver.classify failed: %s", e)
            return {"type": "informative", "reason": f"classification error: {e}", "rewrite": None}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt(message: str, working_memory: Optional[Dict[str, Any]]) -> str:
        """Build the user prompt with rich context for accurate classification and rewriting."""
        parts = [f'Message:\n"""\n{message}\n"""']

        if working_memory:
            context_parts = []

            # User identity
            raw = working_memory.get("raw", {})
            profile = raw.get("user_profile", {})
            if profile:
                context_parts.append(f"User profile: {profile}")

            # Active goals
            if working_memory.get("user_goals"):
                goals = ", ".join(working_memory["user_goals"])
                context_parts.append(f"Active goals: {goals}")

            # Recent events
            events = raw.get("recent_events", [])
            if events:
                event_text = "; ".join(
                    e.get("summary") or e.get("name", "") for e in events[:5]
                )
                context_parts.append(f"Recent events: {event_text}")

            # Session context (WM summary)
            if working_memory.get("context"):
                ctx = working_memory["context"][:400]
                context_parts.append(f"Current context: {ctx}")

            # Emotional baseline
            baseline = working_memory.get("emotional_baseline", "neutral")
            if baseline != "neutral":
                context_parts.append(f"Emotional state: {baseline}")

            if context_parts:
                parts.append("User context (use for rewriting):\n" + "\n".join(context_parts))

        return "\n\n".join(parts)
