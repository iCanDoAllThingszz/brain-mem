"""
Perceiver engine component for the brain-memory service.
Corresponds to the sensory cortex + thalamus in the human brain.

感知器引擎组件 — 对应人脑的感觉皮层+丘脑。

v2: 不仅分类，还将信息型消息重写为高密度、实体明确的记忆输入。
同一query在不同语境下可能有不同含义，因此重写时使用用户画像、工作记忆和长期上下文。

优化历史：
- 2026-03-17: 加强人际关系/组织架构识别规则，提示词中文化
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from server.engine.llm_client import call_llm_json

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是个人记忆系统的感知门户（丘脑）。你有两个任务：

## 任务1：分类
将消息分类为以下三种类型之一：

- "noise"：零个人信息内容。包括纯社交填充词（"嗯嗯"、"好的"、"哈哈"）、通用常识、无个人语境的天气评论。

- "command"：纯指令，不含个人信息。如"翻译这段话"、"查一下天气"、"检查一下日志"。

- "informative"：包含值得记住的用户信息。包括显性信息（事实、决策、计划）和隐性信息（问题透露的兴趣、语气透露的情绪、请求透露的意图）。
  * 混合消息：只要含任何个人信息，分类为"informative"
  * 不确定时 → "informative"（召回优先）

## 任务2：重写（仅当 type = "informative"）
rewrite 将被传给下游评估器，评估器**看不到对话历史，只看 rewrite 本身**。
因此 rewrite 必须完全自洽——读者仅凭 rewrite 就能理解发生了什么，不需要任何额外上下文。

重写规则：
1. **解析所有指代** — "那个"、"之前说的"、"它"、"又失败了"等必须替换为具体实体名称
   * "今天又失败了"（前文提到腾讯面试）→ rewrite 必须写"赵禹今日腾讯面试失败"
   * "上面那个计划"→ rewrite 必须写出计划的具体名称
2. **明确用户主语** — 使用上下文中的真实姓名
3. **关联目标** — 若内容与某个已知目标/计划相关，明确写出关联（为评估器提供 task_relevance 依据）
4. **只陈述事实** — 单次行为不代表习惯，"吃了苹果"≠"有吃水果的习惯"
5. **保留原始意图** — 不改变语义，不过度推断

示例：
- "最近ai agent有啥新动向"（用户有跳槽AI创业公司的计划）
  → "赵禹询问AI Agent最新动态，与其跳槽AI创业公司的职业规划相关"
- "今天又失败了"（session中提到腾讯面试）
  → "赵禹今日腾讯面试失败" ❌ 不要写"赵禹今天又失败了"（指代未解析）
- "帮我搜一下上海AI公司"（用户有跳槽计划）
  → "赵禹正在调研上海AI公司，是其跳槽计划的行动步骤"
- "今天好累"（用户最近面试和工作并行）
  → "赵禹表达疲惫感，可能与近期面试和工作双线压力有关"
- "早上我吃了一个苹果"
  → "赵禹早上吃了一个苹果" ❌ 不要写成"有吃水果的习惯"

noise/command 类型的 rewrite 为 null。

## category 分类（仅 type = "informative" 时填写）

**cognition**：影响用户画像、目标、决策、关系或里程碑的信息。经过重要性评估再决定是否编码。
  - 决策和计划总是 cognition（即使与饮食/运动相关）
  - 引入新人物、描述关系、组织架构变动 → 必须是 cognition
  - 示例："我决定学Rust"、"腾讯面试过了"、"凡哥是我的直属leader"、"梦阳今天提离职了"

**log**：已发生的事件/活动记录，直接编码无需评估。设置 target_entities 为消息中明确提及的实体，供下游映射到图谱精确节点。
  - 饮食记录："吃了苹果"、"午餐牛肉面600大卡" → target_entities=["苹果"] / ["牛肉面"]
  - 运动记录："跑了5公里" → target_entities=null（无具体实体）
  - 面试记录："腾讯二面聊了分布式系统" → target_entities=["腾讯", "分布式系统"]
  - 交易记录："买了0.1个BTC" → target_entities=["BTC"]
  - 学习记录："今天学了Rust的所有权机制" → target_entities=["Rust"]（注意：学习决策是 cognition）
  - 其他日常事件记录

**reconsolidation**：纠正、补充或重新诠释之前的记忆。必须设置 target_entities 和 correction_type。
  target_entities 是用户消息中**明确提及**的实体名称列表（直接从文本提取，不要推断图谱节点）。
  - "correct"：事实纠正 — "不对，我当时说的是感觉很好"
  - "supplement"：补充信息 — "腾讯一面过了，下周二面" → target_entities=["腾讯一面"]
  - "reframe"：情感重构 — "美团那段时间其实很痛苦" → target_entities=["美团"]

**prospective**：设置未来提醒。必须设置 trigger_type / trigger_value / action：
  - trigger_type: "time" | "event" | "condition"
  - trigger_value: ISO时间（UTC+8）、事件关键词或条件表达式
  - action: 触发时要做的事
  - 示例："明天9点提醒我交报告" → time / 2026-03-20T09:00:00+08:00 / 提醒交报告

**forget**：主动抑制某个记忆。必须设置 target_entities（从用户消息中直接提取，不要推断）。
  - "忘掉张三" → target_entities=["张三"]
  - "删掉关于前公司的记忆" → target_entities=["前公司"]

返回格式（仅 JSON）：
{
  "type": "noise" | "command" | "informative",
  "category": "cognition" | "log" | "reconsolidation" | "prospective" | "forget",
  "target_entities": ["消息中明确提及的实体名1", "实体名2"] | null,
  "correction_type": "correct" | "supplement" | "reframe" | null,
  "trigger_type": "time" | "event" | "condition" | null,
  "trigger_value": "触发条件" | null,
  "action": "要做的事" | null,
  "reason": "一句话解释",
  "rewrite": "高密度记忆陈述" | null
}

字段规则：
- noise / command：所有字段为 null
- cognition：target_entities 提取消息中明确出现的实体（用于图谱映射），无则 null；其余字段为 null
  示例："凡哥是我直属leader" → target_entities=["凡哥"]；"今天好累" → target_entities=null
- log：target_entities 提取消息中明确出现的实体（用于图谱映射），无则 null；其余字段为 null
  示例："腾讯二面聊了分布式系统" → target_entities=["腾讯","分布式系统"]
- reconsolidation：必须 target_entities（从文本提取，可多个）+ correction_type，其余为 null
  示例："不对，腾讯和字节面试都很顺利" → target_entities=["腾讯面试","字节面试"]
- prospective：必须 trigger_type + trigger_value + action；target_entities 提取消息中涉及的实体（用于图谱关联），无则 null
  示例："下次见到凡哥时提醒我问项目进度" → target_entities=["凡哥"]；"明天9点提醒我交报告" → target_entities=null
- forget：必须 target_entities（从文本提取，可多个），其余为 null
  示例："忘掉张三和李四" → target_entities=["张三","李四"]

"""


class Perceiver:
    """
    感知器 v2 — 分类并重写消息。
    
    对于信息型消息，生成高密度重写，使隐含信息显式化，
    使用用户上下文进行消歧。
    
    Sensory gateway v2 — classifies AND rewrites messages.
    For informative messages, produces a high-density rewrite that makes
    implicit information explicit, using user context for disambiguation.
    """

    async def classify(
        self,
        message: str,
        working_memory: Optional[Dict[str, Any]] = None,
        assistant_response: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        分类并可选地重写消息。
        
        Classify and optionally rewrite a message.

        Returns:
            Dict with keys:
                - "type": "noise" | "command" | "informative"
                - "category": "cognition" | "log_*" | "reconsolidation" — 信息类别
                - "target_entities": list[str] | None — 消息中提及的实体（cognition/log/reconsolidation/forget使用）
                - "correction_type": str | None — reconsolidation的纠正类型："correct" | "supplement" | "reframe"
                - "reason": str — 分类原因
                - "rewrite": str | None — 信息型消息的高密度重写
        """
        user_prompt = self._build_prompt(message, working_memory, assistant_response)
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

            # Extract category and target_entities
            category = result.get("category", "cognition")
            valid_categories = {"cognition", "log", "reconsolidation", "prospective", "forget"}
            if category not in valid_categories:
                logger.warning("Unexpected category '%s', defaulting to cognition", category)
                category = "cognition"

            raw_entities = result.get("target_entities")
            correction_type = result.get("correction_type")
            trigger_type = result.get("trigger_type")
            trigger_value = result.get("trigger_value")
            action = result.get("action")

            def _normalize_entities(val) -> Optional[List[str]]:
                """Normalize LLM output to list[str] or None."""
                if not val:
                    return None
                if isinstance(val, str):
                    return [val] if val.strip() else None
                if isinstance(val, list):
                    cleaned = [str(item).strip() for item in val if item and str(item).strip()]
                    return cleaned if cleaned else None
                return None

            # Validate fields based on category
            if msg_type != "informative":
                target_entities = None
                correction_type = None
                trigger_type = None
                trigger_value = None
                action = None
            elif category in {"cognition", "log"}:
                # Extract entities for downstream graph mapping; no correction/trigger fields
                target_entities = _normalize_entities(raw_entities)
                correction_type = None
                trigger_type = None
                trigger_value = None
                action = None
            elif category == "forget":
                # Forget requires target_entities
                target_entities = _normalize_entities(raw_entities)
                if not target_entities:
                    logger.warning("Forget missing target_entities, defaulting to command")
                    msg_type = "command"
                    category = "cognition"
                    target_entities = None
                correction_type = None
                trigger_type = None
                trigger_value = None
                action = None
            elif category == "reconsolidation":
                # Reconsolidation requires both target_entities and correction_type
                target_entities = _normalize_entities(raw_entities)
                if not target_entities:
                    logger.warning("Reconsolidation missing target_entities, defaulting to cognition")
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
                target_entities = _normalize_entities(raw_entities)
                correction_type = None
            else:
                target_entities = None
                correction_type = None
                trigger_type = None
                trigger_value = None
                action = None

            return {
                "type": msg_type,
                "category": category,
                "target_entities": target_entities,
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
                "target_entities": None,
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
    def _build_prompt(
        message: str,
        working_memory: Optional[Dict[str, Any]],
        assistant_response: Optional[str] = None,
    ) -> str:
        """Build the user prompt with rich context for accurate classification and rewriting."""
        parts = [f'User Message:\n"""\n{message}\n"""']

        if assistant_response and assistant_response.strip():
            parts.append(f'Assistant response (本次的agent回复，用于辅助判断消息意图和重写):\n"""\n{assistant_response[:600]}\n"""')

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

            # Emotional baseline
            baseline = working_memory.get("emotional_baseline", "neutral")
            context_parts.append(f"Emotional state: {baseline}")

            if context_parts:
                parts.append("User context (use for rewriting):\n" + "\n".join(context_parts))

            # Messages encoded earlier in this session (intra-session context)
            session_msgs = working_memory.get("session_messages", [])
            if session_msgs:
                lines = "\n".join(f"- {m}" for m in session_msgs[-5:])
                parts.append(f"Earlier in this session (已编码的历史消息，用于理解指代和上下文):\n{lines}")

        return "\n\n".join(parts)
