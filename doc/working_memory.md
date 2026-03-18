# working_memory.py - 工作记忆

## 文件整体功能

`WorkingMemory` 是 brain-memory 服务的工作记忆组件，对应人脑的短期记忆缓存。

**核心职责：**
- 会话级别的背景上下文缓存（session-level context cache）
- 冷启动加载：从长期记忆中提取关键信息
- 增量更新：会话过程中动态更新上下文
- 会话结束时销毁

**设计理念：**
- 工作记忆是AI助手的"当前意识"
- 在会话开始时加载一次（cold boot）
- 会话过程中增量更新
- 会话结束时销毁（不持久化）

---

## 类：WorkingMemory

### 作用
会话级别的工作记忆，AI助手的短期上下文缓存。

### 类属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `_cache` | Dict[str, Dict[str, Any]] | 类级别的内存缓存：session_id → context dict |

### 初始化方法

```python
def __init__(self, graph: GraphStore, buffer: EncoderBuffer) -> None
```

**参数：**
- `graph`: GraphStore 实例，用于查询长期记忆
- `buffer`: EncoderBuffer 实例，用于查询最近会话摘要

---

## 核心方法

### 1. load - 冷启动加载工作记忆

```python
async def load(
    self,
    tenant_id: str,
    user_id: str,
    session_id: str,
    user_profile: Optional[Dict[str, Any]] = None,
    agent_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]
```

**功能：** 为新会话冷启动加载工作记忆。

**参数：**
- `tenant_id`: 租户ID
- `user_id`: 用户ID
- `session_id`: 新会话ID
- `user_profile`: 可选的预加载用户档案
- `agent_context`: 可选的额外agent上下文

**返回值：**
```python
{
    "context": str,                    # 自然语言背景上下文
    "pending_reminders": List[str],    # 待处理提醒列表
    "pending_reviews": List[str],      # 待复习记忆列表
    "user_goals": List[str],           # 活跃目标列表
    "emotional_baseline": str,         # 情绪基线（positive/negative/neutral）
    "raw": Dict[str, Any],             # 原始数据（供其他引擎组件使用）
    "session_id": str,                 # 会话ID
    "tenant_id": str,                  # 租户ID
    "user_id": str,                    # 用户ID
    "loaded_at": str,                  # 加载时间（ISO格式）
}
```

**执行流程：**
1. 从长期记忆中提取关键信息：
   - 用户核心档案（使用传入的 `user_profile` 或空字典）
   - 活跃目标（标签为"计划"或"目标"，状态为active）
   - 最近关键事件（最近7天的episodic节点，按重要性排序，取前5个）
   - 情绪基线（从最近事件的emotional_tag统计）
   - 上次会话摘要（从buffer中获取）
   - 待处理提醒（标签为"计划"/"提醒"，状态为pending）
   - 待复习记忆（间隔重复系统标记的needs_review节点）
2. 使用LLM合成自然语言上下文（3-5句话）
3. 缓存到类级别的 `_cache` 字典
4. 返回工作记忆字典

**代码示例：**
```python
# 加载工作记忆
wm = await working_memory.load(
    tenant_id="tenant_001",
    user_id="user_001",
    session_id="session_123",
    user_profile={"name": "赵禹", "age": 29},
)
# 结果：
# {
#     "context": "赵禹，29岁，正在准备跳槽面试。当前活跃目标：减肥计划（目标85kg）、面试准备（8周计划）。最近情绪偏负面，对当前工作不满。待处理提醒：明天10点面试。",
#     "pending_reminders": ["明天10点面试"],
#     "pending_reviews": ["Java并发编程知识点"],
#     "user_goals": ["减肥计划", "面试准备"],
#     "emotional_baseline": "negative",
#     "raw": {...},
#     "session_id": "session_123",
#     "loaded_at": "2026-03-18T06:38:00Z"
# }
```

**调用链路：**
- 被调用：会话开始时（API层）
- 调用：
  - `self._fetch_active_goals()` → 获取活跃目标
  - `self._fetch_recent_events()` → 获取最近事件
  - `self._compute_emotional_baseline()` → 计算情绪基线
  - `self.buffer.get_latest_session_summary()` → 获取上次会话摘要
  - `self._fetch_pending_reminders()` → 获取待处理提醒
  - `self._fetch_pending_reviews()` → 获取待复习记忆
  - `self._synthesize_context()` → LLM合成上下文

---

### 2. get - 获取工作记忆

```python
def get(self, session_id: str) -> Optional[Dict[str, Any]]
```

**功能：** 获取活跃会话的工作记忆。

**参数：**
- `session_id`: 会话ID

**返回值：**
- 工作记忆字典，如果未加载则返回 `None`

**代码示例：**
```python
wm = working_memory.get("session_123")
if wm:
    print(wm["context"])
```

---

### 3. update - 增量更新工作记忆

```python
def update(self, session_id: str, updates: Dict[str, Any]) -> None
```

**功能：** 在会话过程中增量更新工作记忆。

**参数：**
- `session_id`: 会话ID
- `updates`: 要更新/添加的字段字典

**执行流程：**
1. 检查会话是否已加载
2. 合并 `updates` 到现有工作记忆
3. 如果 `updates` 包含 `raw` 字段，也合并到 `raw` 子字典

**代码示例：**
```python
# 更新情绪基线
working_memory.update("session_123", {
    "emotional_baseline": "positive",
    "raw": {"recent_achievement": "完成面试"}
})
```

**注意事项：**
- 如果会话未加载，更新会被静默忽略
- 更新是浅合并（shallow merge）

---

### 4. destroy - 销毁工作记忆

```python
def destroy(self, session_id: str) -> None
```

**功能：** 销毁已完成会话的工作记忆。

**参数：**
- `session_id`: 要销毁的会话ID

**代码示例：**
```python
# 会话结束时
working_memory.destroy("session_123")
```

---

## 内部辅助方法

### 1. _fetch_active_goals - 获取活跃目标

```python
async def _fetch_active_goals(
    self, tenant_id: str, user_id: str
) -> List[Dict[str, Any]]
```

**功能：** 获取标签为"计划"或"目标"且状态为active的节点。

**返回值：**
```python
[
    {
        "id": str,
        "name": str,
        "summary": str,
        "tags": List[str]
    },
    ...
]
```

**限制：** 最多返回10个目标（去重）

---

### 2. _fetch_recent_events - 获取最近事件

```python
async def _fetch_recent_events(
    self, tenant_id: str, user_id: str, days: int = 7, top_n: int = 5
) -> List[Dict[str, Any]]
```

**功能：** 获取最近N天的episodic节点，按重要性排序。

**参数：**
- `days`: 时间范围（默认7天）
- `top_n`: 最多返回数量（默认5个）

**返回值：**
```python
[
    {
        "id": str,
        "name": str,
        "summary": str,
        "importance": float,
        "emotional_tag": Dict,
        "created_at": str
    },
    ...
]
```

---

### 3. _fetch_pending_reminders - 获取待处理提醒

```python
async def _fetch_pending_reminders(
    self, tenant_id: str, user_id: str
) -> List[Dict[str, Any]]
```

**功能：** 获取标签为"计划"/"提醒"且状态为pending的节点。

**限制：** 最多返回10个提醒

---

### 4. _fetch_pending_reviews - 获取待复习记忆

```python
async def _fetch_pending_reviews(
    self, tenant_id: str, user_id: str
) -> List[Dict[str, Any]]
```

**功能：** 获取 `properties.needs_review=true` 的节点（间隔重复系统）。

**限制：** 最多返回10个待复习记忆

---

### 5. _compute_emotional_baseline - 计算情绪基线

```python
@staticmethod
def _compute_emotional_baseline(
    recent_events: List[Dict[str, Any]],
) -> str
```

**功能：** 从最近事件的emotional_tag计算情绪基线。

**返回值：** `"positive"` / `"negative"` / `"neutral"`

**计算逻辑：**
```python
positive_types = {"joy", "surprise"}
negative_types = {"sadness", "anger", "fear"}

# 统计高强度（intensity >= 3）的情绪
pos_count = 0
neg_count = 0
for event in recent_events:
    if event.emotional_tag.intensity >= 3:
        if event.emotional_tag.type in positive_types:
            pos_count += 1
        elif event.emotional_tag.type in negative_types:
            neg_count += 1

# 比较正负情绪数量
if pos_count > neg_count:
    return "positive"
elif neg_count > pos_count:
    return "negative"
return "neutral"
```

---

### 6. _synthesize_context - LLM合成上下文

```python
async def _synthesize_context(self, raw: Dict[str, Any]) -> str
```

**功能：** 使用LLM将原始数据合成为自然语言上下文字符串。

**输入：** 原始数据字典（包含用户档案、目标、事件、情绪等）

**输出：** 3-5句话的自然语言上下文（中文）

**LLM提示词要点：**
- 包含5个维度：用户身份、活跃目标、上次会话、情绪状态、待处理事项
- 具体而非泛泛（包含名称、日期、数字）
- 优先可操作的上下文
- 如果目标停滞或逾期，突出显示
- **必须用中文输出**

**代码示例：**
```python
context = await self._synthesize_context({
    "user_profile": {"name": "赵禹", "age": 29},
    "active_goals": [{"name": "减肥计划", "summary": "目标85kg"}],
    "recent_events": [...],
    "emotional_baseline": "negative",
    "pending_reminders": [{"name": "明天10点面试"}],
})
# 结果：
# "赵禹，29岁，正在准备跳槽面试。当前活跃目标：减肥计划（目标85kg）。最近情绪偏负面，对当前工作不满。待处理提醒：明天10点面试。"
```

---

## 调用链路总览

```
会话开始（API层）
    ↓
WorkingMemory.load()
    ↓
    ├─→ _fetch_active_goals() → GraphStore.find_active_nodes()
    ├─→ _fetch_recent_events() → GraphStore.find_active_nodes()
    ├─→ _compute_emotional_baseline() → 统计情绪
    ├─→ buffer.get_latest_session_summary() → 获取上次会话
    ├─→ _fetch_pending_reminders() → GraphStore.find_active_nodes()
    ├─→ _fetch_pending_reviews() → GraphStore.find_active_nodes()
    └─→ _synthesize_context() → LLM合成上下文

会话过程中
    ↓
WorkingMemory.update() → 增量更新上下文

会话结束
    ↓
WorkingMemory.destroy() → 清理缓存
```

---

## 关键逻辑说明

### 1. 冷启动加载（Cold Boot）
```python
# 会话开始时一次性加载
wm = await working_memory.load(...)

# 加载内容：
# 1. 用户档案
# 2. 活跃目标（最多10个）
# 3. 最近事件（7天内，前5个）
# 4. 情绪基线
# 5. 上次会话摘要
# 6. 待处理提醒（最多10个）
# 7. 待复习记忆（最多10个）
```

**设计理由：**
- 避免每次查询都访问图谱（性能优化）
- 提供稳定的会话级上下文
- 减少LLM token消耗

### 2. 增量更新（Incremental Update）
```python
# 会话过程中动态更新
working_memory.update(session_id, {
    "emotional_baseline": "positive",  # 情绪变化
    "raw": {"new_info": "..."}         # 新增信息
})
```

**使用场景：**
- 用户情绪变化
- 新增目标或提醒
- 会话中的重要事件

### 3. LLM上下文合成
```python
# 将结构化数据合成为自然语言
context = await self._synthesize_context(raw_data)

# 输入：
# {
#     "user_profile": {...},
#     "active_goals": [...],
#     "recent_events": [...],
#     "emotional_baseline": "negative",
#     "pending_reminders": [...]
# }

# 输出：
# "赵禹，29岁，正在准备跳槽面试。当前活跃目标：减肥计划（目标85kg）。最近情绪偏负面，对当前工作不满。待处理提醒：明天10点面试。"
```

**设计理由：**
- 自然语言上下文更适合注入到LLM prompt
- 比结构化数据更易于理解
- 减少token消耗（3-5句话 vs 完整JSON）

---

## 使用场景

### 场景1：会话开始时加载
```python
# 用户开始新会话
wm = await working_memory.load(
    tenant_id="tenant_001",
    user_id="user_001",
    session_id="session_123",
)

# 将上下文注入到LLM prompt
prompt = f"""
你是AI助手酪酪。以下是用户的背景上下文：

{wm["context"]}

用户：{user_query}
"""
```

### 场景2：会话过程中更新
```python
# 用户完成了一个目标
working_memory.update("session_123", {
    "user_goals": ["面试准备"],  # 移除已完成的"减肥计划"
    "raw": {"completed_goal": "减肥计划"}
})
```

### 场景3：会话结束时销毁
```python
# 用户结束会话
working_memory.destroy("session_123")
```

---

## 注意事项

1. **会话隔离：** 每个会话有独立的工作记忆，互不干扰
2. **内存管理：** 工作记忆存储在内存中，会话结束时必须销毁
3. **冷启动成本：** 首次加载需要查询图谱和LLM，有一定延迟
4. **增量更新：** 会话过程中的更新是浅合并，不会重新查询图谱
5. **LLM依赖：** 上下文合成依赖LLM，如果LLM失败会回退到结构化文本

---

## 依赖关系

- **依赖：** `GraphStore`（图谱存储）、`EncoderBuffer`（缓冲区）、`LLMClient`（LLM调用）
- **被依赖：** API层（会话管理）、Retriever（检索器）
