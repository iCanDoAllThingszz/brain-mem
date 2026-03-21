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
你是个人记忆系统的记忆价值评估器（对应前额叶皮层+杏仁核）。
任务：判断一条消息是否值得写入长期记忆，并输出三个维度的评分。

## 评分规则

使用 0-10 整数评分，**务必用满全区间，不要扎堆在 3-5**。

### 1. task_relevance（任务关联度）
0-2：与用户任何已知目标无关（闲聊、通用常识）
3-4：涉及用户关注的话题，但未推进具体目标
5-6：中等关联，如某个活跃项目的进展更新
7-8：直接推进关键目标（如"拿到字节面试"、"项目上线了"）
9-10：重大人生决策或里程碑（如"我决定离职"、"拿到 offer 了"）

### 2. emotional_intensity（情绪强度）
**评分时对照用户当前情绪基线**：若某种情绪与基线差异大（如基线低落时出现高兴），强度应上调；若与基线一致（如持续焦虑中又提到焦虑），强度应下调。

0-2：平静中性，陈述事实
3-4：轻微情绪（淡淡的沮丧、小确幸）
5-6：明显情绪（明显开心、明显压力大）
7-8：强烈情绪（非常兴奋、愤怒、哭泣）
9-10：极端情绪（人生级别的喜悦、深度悲痛、恐慌）

emotion_type 必须是以下之一：joy / sadness / anger / fear / surprise / neutral

### 3. novelty（新颖度）
0-2：已知信息、重复事实、上下文中已有记录，或针对临时技术问题的调试提问（转瞬即逝，不值得长期记忆）
3-4：已知话题的细节补充
5-6：有意义的新信息
7-8：令人意外的新进展或事实
9-10：完全超出预期、改变认知的信息

> 若上下文中已有该信息（如画像中已有"在美团工作"），novelty 必须评 0-2。

## 编码决策（按顺序匹配第一条）
- task_relevance >= 7 → encode_decision=true, encode_priority="high"
- emotional_intensity >= 7 → encode_decision=true, encode_priority="high"
- novelty >= 8 → encode_decision=true, encode_priority="medium"
- task_relevance >= 5 OR novelty >= 5 → encode_decision=true, encode_priority="low"
- 其余 → encode_decision=false, encode_priority="low"

## 返回格式（仅 JSON）
{
  "task_relevance": <0-10>,
  "emotional_intensity": <0-10>,
  "emotion_type": "joy|sadness|anger|fear|surprise|neutral",
  "novelty": <0-10>,
  "encode_decision": true|false,
  "encode_priority": "high|medium|low",
  "reason": "一句话解释"
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
        parts = [f'待评估消息：\n"""\n{message}\n"""']

        if working_memory:
            context_parts = []

            raw = working_memory.get("raw", {})

            # User profile
            profile = raw.get("user_profile", {})
            if profile:
                context_parts.append(f"用户画像：{profile}")

            # Active goals
            if working_memory.get("user_goals"):
                goals = "\n".join(f"- {g}" for g in working_memory["user_goals"])
                context_parts.append(f"当前活跃目标：\n{goals}")

            # Recent events
            if raw.get("recent_events"):
                events_text = "; ".join(
                    str(e.get("summary", e.get("name", "")))
                    for e in raw["recent_events"][:5]
                )
                context_parts.append(f"近期关键事件：{events_text}")

            # Emotional baseline — critical for calibrating emotional_intensity
            baseline = working_memory.get("emotional_baseline", "neutral")
            context_parts.append(f"用户当前情绪基线：{baseline}（评分 emotional_intensity 时以此为参照）")

            # Recent session messages for novelty calibration
            session_msgs = working_memory.get("session_messages", [])
            if session_msgs:
                lines = "\n".join(f"- {m}" for m in session_msgs[-5:])
                context_parts.append(f"本 session 已编码的消息（用于判断新颖度）：\n{lines}")

            if context_parts:
                parts.append("用户上下文：\n" + "\n".join(context_parts))

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

        # Re-apply encoding rules deterministically (prompt order: first match wins)
        encode_decision = bool(result.get("encode_decision", False))
        if task_relevance >= 7 or emotional_intensity >= 7:
            encode_decision = True
            encode_priority = "high"
        elif novelty >= 8:
            encode_decision = True
            encode_priority = "medium"
        elif task_relevance >= 5 or novelty >= 5:
            encode_decision = True
            if encode_priority != "high":
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
