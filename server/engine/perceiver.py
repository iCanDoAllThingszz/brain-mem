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
from typing import Any, Dict, Optional

from server.engine.llm_client import call_llm_json

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
\
你是个人记忆系统的感知门户（丘脑）。你有两个任务：

## 任务1：分类
将消息分类为以下三种类型之一：

- "noise"（噪音）：零个人信息内容。包括：
  * 纯社交填充词："嗯嗯"、"好的"、"哈哈"、"OK"、"收到"
  * 通用常识："地球是圆的"、"天是蓝的"、"水是H2O"
  * 无个人语境的天气/时间评论

- "command"（指令）：纯指令，不包含个人信息。\
  包括临时技术问题的调试/排查查询。\
  示例："翻译这段话"、"查一下天气"、"检查一下日志"、"为什么会有两个服务"

- "informative"（信息型）：包含值得记住的用户信息。\
  包括显性信息（事实、决策、计划）和隐性信息（问题透露的兴趣、语气透露的情绪、请求透露的意图）。

关键规则：
- 问题透露兴趣："最近AI agent有啥新动向" → 用户对AI agent感兴趣
- 指令透露意图："帮我搜上海AI公司" → 用户在调研AI公司
- 情绪透露状态："今天好累" → 用户疲惫
- 混合消息：如果包含任何个人信息，分类为"informative"
- 不确定时 → "informative"（召回优先原则）

## 任务2：重写（仅当type = "informative"时）
将原始消息重写为高密度记忆陈述，要求：
1. 明确用户（主语）— 使用上下文中的真实姓名
2. 记录陈述的事实 — 不要将单次事件泛化为习惯或偏好
3. 关联已知上下文（目标、近期事件、职业计划）
4. 去除常识噪音，只保留个人相关部分
5. 明确实体关系
6. **保留原始意图** — 不要过度推断或改变语义。\
   如果用户在质疑/怀疑，保持那个语气。\
   如果用户在陈述事实，保持事实性。\
   不确定意图时，优先选择更字面的重写而非推测。
7. **禁止过度推断** — 单次行为不代表习惯或偏好。\
   "吃了一个苹果"意味着吃了一次苹果，不是"有吃水果的习惯"。\
   "跑了5公里"意味着跑了一次5公里，不是"经常锻炼"。\
   只陈述明确说的内容。模式识别是巩固器的工作，不是你的。

示例：
- 原文："最近ai agent有啥新动向"
  上下文：用户是赵禹，计划跳槽AI创业公司
  重写："赵禹询问AI Agent最新动态，表明他持续关注AI Agent领域，与跳槽AI创业公司的职业规划相关"

- 原文："帮我搜一下上海AI公司"
  上下文：用户计划搬到上海
  重写："赵禹正在调研上海AI公司，这是他跳槽计划的具体行动步骤"

- 原文："今天好累"
  上下文：用户最近忙于面试和工作
  重写："赵禹表达疲惫感，可能与近期面试和工作双线压力有关"

- 原文："地球是圆的，对了我打算学Rust"
  重写："赵禹计划学习Rust语言以拓展技术栈"

- 原文："好的 明天开始记录饮食"
  上下文：用户有减肥计划，已停滞4天
  重写："赵禹承诺明天重新开始记录饮食，减肥计划即将恢复"

- 原文："早上我吃了一个苹果"
  重写："赵禹早上吃了一个苹果"
  ❌ 错误："赵禹有早餐吃水果的习惯"（从单次事件过度推断）

- 原文："我今天中午吃了一碗牛肉面 大概600大卡"
  重写："赵禹今日午餐吃了一碗牛肉面，约600大卡"
  ❌ 错误："赵禹喜欢吃牛肉面"（过度推断）

- 原文："怎么会有两个服务 不是就一个服务吗"
  上下文：用户在调试记忆系统项目
  重写："赵禹对系统中存在两个服务表示疑惑，认为应该只有一个服务"

对于"noise"或"command"类型，rewrite应为null。

返回格式（仅JSON）：
{
  "type": "noise" | "command" | "informative",
  "category": "cognition" | "log_diet" | "log_exercise" | "log_interview" | "log_trading" | "log_learning" | "log_general" | "reconsolidation" | "prospective" | "forget",
  "target_entity": "需要更新的实体名称（如'减肥计划'、'跳槽计划'）" | null,
  "correction_type": "correct" | "supplement" | "reframe" | null,
  "trigger_type": "time" | "event" | "condition" | null,
  "trigger_value": "具体触发条件" | null,
  "action": "要做的事" | null,
  "reason": "一句话分类解释",
  "rewrite": "重写后的高密度记忆陈述" | null
}

分类规则：
- "cognition"（认知）：直接影响用户画像、目标、决策、关系或里程碑的信息。\
  重要：决策和计划总是cognition，即使它们与学习/锻炼/饮食相关。\
  **关键**：任何引入新人物、描述关系或解释组织动态的消息必须是"cognition"，不是"log"。包括：\
    * 新同事、朋友、家人及其角色/背景
    * 汇报线、团队组成、组织架构
    * 谁和谁一起工作、谁管理谁、谁向谁汇报
    * 团队动态、人事变动、离职
  示例："我决定学Rust" → cognition（决策），"我打算开始减肥" → cognition（计划），\
  "腾讯面试过了" → cognition（里程碑），\
  "凡哥是我的直属leader" → cognition（关系），\
  "梦阳今天提离职了" → cognition（人事变动），\
  "少栋是我的虚线，鹏程是我同事" → cognition（组织架构）
  
- "log_diet"（饮食日志）：仅实际饮食/食物消费记录。如"吃了苹果"、"午餐牛肉面600大卡"。\
  默认target_entity："减肥计划"
  
- "log_exercise"（运动日志）：仅实际运动/锻炼记录。如"跑了5公里"、"做了30个俯卧撑"。\
  默认target_entity："减肥计划"
  
- "log_interview"（面试日志）：仅面试会话细节/反馈。如"腾讯二面聊了分布式系统"。\
  默认target_entity："跳槽计划"
  
- "log_trading"（交易日志）：仅交易记录或市场观察。如"买了0.1个BTC"。\
  默认target_entity："量化交易"
  
- "log_learning"（学习日志）：仅实际学习笔记或学习记录。如"今天学了Rust的所有权机制"。\
  不是学习决策（那是cognition）。
  
- "log_general"（通用日志）：不符合上述类别的其他日志型信息

- "reconsolidation"（记忆重固化）：用户在纠正、补充或重新诠释之前的记忆。\
  这是记忆重固化 — 基于新语境更新已有信息。\
  总是设置target_entity为被纠正的实体。\
  总是设置correction_type：\
    * "correct"：事实纠正（如"不对，我当时说的是感觉很好"）\
    * "supplement"：添加新信息（如"腾讯一面过了，下周二面"）\
    * "reframe"：情感重新诠释（如"美团那段时间其实很痛苦"）
    
- "prospective"（前瞻记忆）：用户在设置未来的提醒或意图。\
  这是前瞻记忆 — 记住稍后要做的事。\
  总是设置trigger_type：\
    * "time"：基于时间的触发（如"明天提醒我交报告" → trigger_value="2026-03-15 09:00"）\
    * "event"：基于事件的触发（如"下次聊到面试时问问字节结果" → trigger_value="面试"）\
    * "condition"：基于条件的触发（如"如果BTC跌破6万提醒我" → trigger_value="BTC<60000"）\
  总是设置trigger_value：具体触发条件（ISO格式时间、事件关键词或条件表达式）\
  总是设置action：触发时要做什么（如"提醒交报告"、"问字节面试结果"）\
  对于时间触发，将相对时间如"明天"、"下周"解析为绝对ISO datetime（北京时间UTC+8）。\
  示例：\
    * "明天早上9点提醒我交报告" → trigger_type="time", trigger_value="2026-03-15T09:00:00+08:00", action="提醒交报告"\
    * "下次聊到减肥时提醒我记录饮食" → trigger_type="event", trigger_value="减肥", action="提醒记录饮食"\
    * "如果BTC跌破6万提醒我" → trigger_type="condition", trigger_value="BTC<60000", action="提醒BTC跌破6万"
    
- "forget"（遗忘）：用户想要遗忘或抑制某个记忆。\
  这是动机性遗忘 — 主动抑制不想要的记忆。\
  总是设置target_entity：要遗忘的实体/记忆（如"张三"、"那次失败的面试"）\
  示例：\
    * "忘掉张三这个人" → category="forget", target_entity="张三"\
    * "不要再提那次失败的面试" → category="forget", target_entity="那次失败的面试"\
    * "删掉关于前公司的记忆" → category="forget", target_entity="前公司"

对于log类别，总是设置target_entity（不确定时使用上述默认值）。
对于reconsolidation类别，总是设置target_entity和correction_type。
对于prospective类别，总是设置trigger_type、trigger_value和action。
对于forget类别，总是设置target_entity。
对于cognition类别或noise/command类型，target_entity和correction_type应为null。

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
    ) -> Dict[str, Any]:
        """
        分类并可选地重写消息。
        
        Classify and optionally rewrite a message.

        Returns:
            Dict with keys:
                - "type": "noise" | "command" | "informative"
                - "category": "cognition" | "log_*" | "reconsolidation" — 信息类别
                - "target_entity": str | None — log/reconsolidation类别需要更新的实体
                - "correction_type": str | None — reconsolidation的纠正类型："correct" | "supplement" | "reframe"
                - "reason": str — 分类原因
                - "rewrite": str | None — 信息型消息的高密度重写
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
