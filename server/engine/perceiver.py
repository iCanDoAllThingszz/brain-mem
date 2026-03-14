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
  "category": "cognition" | "log_diet" | "log_exercise" | "log_interview" | "log_trading" | "log_learning" | "log_general" | "reconsolidation" | "prospective" | "forget",
  "target_entity": "entity name that should be updated (e.g., '减肥计划', '跳槽计划')" | null,
  "correction_type": "correct" | "supplement" | "reframe" | null,
  "trigger_type": "time" | "event" | "condition" | null,
  "trigger_value": "具体触发条件" | null,
  "action": "要做的事" | null,
  "reason": "one-sentence classification explanation",
  "rewrite": "rewritten high-density memory statement" | null
}

Category rules:
- "cognition": Information that directly affects user profile, goals, DECISIONS, relationships, or milestones. \
  IMPORTANT: Decisions and plans are ALWAYS cognition, even if they relate to learning/exercise/diet. \
  Examples: "我决定学Rust" → cognition (decision), "我打算开始减肥" → cognition (plan), \
  "腾讯面试过了" → cognition (milestone)
- "log_diet": ONLY actual diet/food consumption records. E.g., "吃了苹果", "午餐牛肉面600大卡". \
  Default target_entity: "减肥计划"
- "log_exercise": ONLY actual exercise/workout records. E.g., "跑了5公里", "做了30个俯卧撑". \
  Default target_entity: "减肥计划"
- "log_interview": ONLY interview session details/feedback. E.g., "腾讯二面聊了分布式系统". \
  Default target_entity: "跳槽计划"
- "log_trading": ONLY trading records or market observations. E.g., "买了0.1个BTC". \
  Default target_entity: "量化交易"
- "log_learning": ONLY actual study notes or learning records. E.g., "今天学了Rust的所有权机制". \
  NOT decisions to learn something (that's cognition).
- "log_general": Other log-type information that doesn't fit above categories
- "reconsolidation": User is correcting, supplementing, or reframing a PREVIOUS memory. \
  This is memory reconsolidation — updating existing information based on new context. \
  ALWAYS set target_entity to the entity being corrected. \
  ALWAYS set correction_type: \
    * "correct": Factual correction (e.g., "不对，我当时说的是感觉很好") \
    * "supplement": Adding new information (e.g., "腾讯一面过了，下周二面") \
    * "reframe": Emotional reinterpretation (e.g., "美团那段时间其实很痛苦")
- "prospective": User is setting a reminder or intention for the FUTURE. \
  This is prospective memory — remembering to do something later. \
  ALWAYS set trigger_type: \
    * "time": Time-based trigger (e.g., "明天提醒我交报告" → trigger_value="2026-03-15 09:00") \
    * "event": Event-based trigger (e.g., "下次聊到面试时问问字节结果" → trigger_value="面试") \
    * "condition": Condition-based trigger (e.g., "如果BTC跌破6万提醒我" → trigger_value="BTC<60000") \
  ALWAYS set trigger_value: The specific trigger condition (time in ISO format, event keyword, or condition expression) \
  ALWAYS set action: What to do when triggered (e.g., "提醒交报告", "问字节面试结果") \
  For time triggers, parse relative times like "明天", "下周" into absolute ISO datetime (Beijing time UTC+8). \
  Examples: \
    * "明天早上9点提醒我交报告" → trigger_type="time", trigger_value="2026-03-15T09:00:00+08:00", action="提醒交报告" \
    * "下次聊到减肥时提醒我记录饮食" → trigger_type="event", trigger_value="减肥", action="提醒记录饮食" \
    * "如果BTC跌破6万提醒我" → trigger_type="condition", trigger_value="BTC<60000", action="提醒BTC跌破6万"
- "forget": User wants to FORGET or SUPPRESS a memory. \
  This is motivated forgetting — actively suppressing unwanted memories. \
  ALWAYS set target_entity: The entity/memory to forget (e.g., "张三", "那次失败的面试") \
  Examples: \
    * "忘掉张三这个人" → category="forget", target_entity="张三" \
    * "不要再提那次失败的面试" → category="forget", target_entity="那次失败的面试" \
    * "删掉关于前公司的记忆" → category="forget", target_entity="前公司"

For log categories, ALWAYS set target_entity (use the defaults above if unsure).
For reconsolidation category, ALWAYS set target_entity and correction_type.
For prospective category, ALWAYS set trigger_type, trigger_value, and action.
For forget category, ALWAYS set target_entity.
For cognition category or noise/command types, target_entity and correction_type should be null.
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
                - "category": "cognition" | "log_*" | "reconsolidation" — information category
                - "target_entity": str | None — entity to update for log/reconsolidation categories
                - "correction_type": str | None — "correct" | "supplement" | "reframe" for reconsolidation
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

            # Extract category and target_entity
            category = result.get("category", "cognition")
            valid_categories = {
                "cognition", "log_diet", "log_exercise", "log_interview",
                "log_trading", "log_learning", "log_general", "reconsolidation", "prospective", "forget"
            }
            if category not in valid_categories:
                logger.warning("Unexpected category '%s', defaulting to cognition", category)
                category = "cognition"

            target_entity = result.get("target_entity")
            correction_type = result.get("correction_type")
            trigger_type = result.get("trigger_type")
            trigger_value = result.get("trigger_value")
            action = result.get("action")

            # Validate target_entity and correction_type based on category
            if msg_type != "informative" or category == "cognition":
                target_entity = None
                correction_type = None
                trigger_type = None
                trigger_value = None
                action = None
            elif category == "forget":
                # Forget requires target_entity
                if not target_entity:
                    logger.warning("Forget missing target_entity, defaulting to command")
                    msg_type = "command"
                    category = "cognition"
                    target_entity = None
                correction_type = None
                trigger_type = None
                trigger_value = None
                action = None
            elif category == "reconsolidation":
                # Reconsolidation requires both target_entity and correction_type
                if not target_entity:
                    logger.warning("Reconsolidation missing target_entity, defaulting to cognition")
                    category = "cognition"
                    correction_type = None
                elif correction_type not in {"correct", "supplement", "reframe"}:
                    logger.warning("Invalid correction_type '%s', defaulting to 'correct'", correction_type)
                    correction_type = "correct"
                trigger_type = None
                trigger_value = None
                action = None
            elif category == "prospective":
                # Prospective requires trigger_type, trigger_value, and action
                if not trigger_type or not trigger_value or not action:
                    logger.warning("Prospective missing required fields, defaulting to cognition")
                    category = "cognition"
                    trigger_type = None
                    trigger_value = None
                    action = None
                elif trigger_type not in {"time", "event", "condition"}:
                    logger.warning("Invalid trigger_type '%s', defaulting to cognition", trigger_type)
                    category = "cognition"
                    trigger_type = None
                    trigger_value = None
                    action = None
                target_entity = None
                correction_type = None
            else:
                # Other categories don't use correction_type or prospective fields
                correction_type = None
                trigger_type = None
                trigger_value = None
                action = None

            return {
                "type": msg_type,
                "category": category,
                "target_entity": target_entity,
                "correction_type": correction_type,
                "trigger_type": trigger_type,
                "trigger_value": trigger_value,
                "action": action,
                "reason": result.get("reason", ""),
                "rewrite": rewrite,
            }
        except Exception as e:
            logger.error("Perceiver.classify failed: %s", e)
            return {
                "type": "informative",
                "category": "cognition",
                "target_entity": None,
                "correction_type": None,
                "trigger_type": None,
                "trigger_value": None,
                "action": None,
                "reason": f"classification error: {e}",
                "rewrite": None
            }

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
