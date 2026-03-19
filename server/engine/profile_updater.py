"""
ProfileUpdater — LLM-driven incremental user profile and goals manager.

After each successfully encoded conversation turn, inspects the encoded
message and decides whether/how to update the persistent user profile and
goals stored in UserProfileStore.

Design principles:
- Conservative: only update what the new message clearly indicates
- Non-destructive: never delete goals unless user explicitly abandons them
- Incremental: supplement existing fields rather than overwrite them
"""

import json
import logging
from typing import Any, Dict, Optional

from server.engine.llm_client import call_llm_json
from server.storage.user_profile import UserProfileStore

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是用户画像管理器。根据一条新编码的记忆，决定如何更新用户画像和目标列表。

## 用户画像（profile）可包含的字段
- name: 姓名
- occupation: 职业/职位
- company: 所在公司
- location: 城市/地区
- background: 背景描述（技能、经历摘要等）
- preferences: 工具/习惯偏好
- 其他你认为值得长期记录的稳定属性

## 目标列表（goals）格式
每条目标：{"name": "目标名称", "status": "active|completed|paused", "progress": "当前进展描述"}

## 更新规则
1. 保守原则：只更新新记忆明确涉及的字段，其余字段照原样返回
2. 不删除：除非用户明确放弃或完成某目标，否则保留现有目标
3. 渐进补充：用新信息丰富已有字段，而不是覆盖
4. 目标进展：若新记忆涉及某目标的具体进展（面试通过、完成训练等），更新该目标的 progress
5. 新目标：若新记忆明确提到全新计划，添加到 goals
6. 忽略噪音：与用户画像无关的日常琐事不应修改 profile 的稳定字段
7. changed 字段：若无任何更改，返回 "changed": false，这样可跳过写库

只返回合法 JSON，不要有任何说明文字：
{
  "profile": { ...完整的更新后画像... },
  "goals":   [ ...完整的更新后目标列表... ],
  "changed": true | false
}
"""


class ProfileUpdater:
    """
    Incrementally enriches the persistent user profile and goals after each
    successfully encoded message. Runs as a fire-and-forget background task.
    """

    def __init__(self, profile_store: UserProfileStore) -> None:
        self.store = profile_store

    async def update(
        self, tenant_id: str, user_id: str, encoded_message: str
    ) -> Optional[Dict[str, Any]]:
        """
        Read current profile/goals, ask LLM whether to update them,
        save if anything changed, and return the updated values so the
        caller can refresh the in-memory WM cache immediately.

        Returns {"profile": dict, "goals": list} if updated, else None.
        """
        current = self.store.get(tenant_id, user_id)
        profile = current["profile"]
        goals = current["goals"]

        user_prompt = (
            f"当前用户画像：\n{_fmt(profile)}\n\n"
            f"当前目标列表：\n{_fmt(goals)}\n\n"
            f"新编码记忆：\n\"\"\"\n{encoded_message}\n\"\"\""
        )

        try:
            result = await call_llm_json(_SYSTEM_PROMPT, user_prompt)

            if not isinstance(result, dict):
                logger.warning("ProfileUpdater: unexpected LLM response type %s", type(result))
                return None

            # LLM decided nothing needs updating
            if result.get("changed") is False:
                return None

            new_profile = result.get("profile", profile)
            new_goals = result.get("goals", goals)

            if not isinstance(new_profile, dict) or not isinstance(new_goals, list):
                logger.warning("ProfileUpdater: invalid response shape, skipping")
                return None

            self.store.save(tenant_id, user_id, new_profile, new_goals)
            logger.info("ProfileUpdater: updated profile for %s/%s", tenant_id, user_id)
            return {"profile": new_profile, "goals": new_goals}

        except Exception as e:
            logger.warning("ProfileUpdater.update failed: %s", e)
            return None


def _fmt(obj: Any) -> str:
    if not obj:
        return "（空）"
    return json.dumps(obj, ensure_ascii=False, indent=2)