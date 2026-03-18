# prospective_checker.py - 前瞻性记忆检查器

## 文件整体功能

`ProspectiveChecker` 是 brain-memory 服务的前瞻性记忆检查器，负责监控和触发待处理的提醒。

**核心职责：**
- 检查基于时间的触发器（time-based triggers）
- 检查基于事件的触发器（event-based triggers）
- 自动更新触发器状态（pending → completed）

**前瞻性记忆（Prospective Memory）：**
- 指"记得要做某事"的能力（如"明天10点提醒我开会"）
- 与回顾性记忆（Retrospective Memory）相对，后者是"记得已经做过的事"

---

## 类：ProspectiveChecker

### 作用
前瞻性记忆检查器，监控并触发待处理的提醒。

### 初始化方法

```python
def __init__(self, graph: GraphStore) -> None
```

**参数：**
- `graph`: GraphStore 实例，用于查询和更新图谱节点

---

## 核心方法

### 1. check_time_triggers - 检查时间触发器

```python
async def check_time_triggers(
    self,
    tenant_id: str,
    user_id: str,
) -> List[Dict[str, Any]]
```

**功能：** 检查所有到期的时间触发器。

**参数：**
- `tenant_id`: 租户ID
- `user_id`: 用户ID

**返回值：**
```python
[
    {
        "node_id": str,        # 节点ID
        "action": str,         # 提醒动作（如"提醒禹哥面试"）
        "trigger_value": str,  # 触发时间（ISO格式）
        "trigger_type": "time" # 触发类型
    },
    ...
]
```

**执行流程：**
1. 获取当前北京时间（UTC+8）
2. 查询图谱中所有待处理的时间触发器：
   - `zone = 'procedural'`（程序性记忆区）
   - `'提醒' in tags`
   - `properties.trigger_type = 'time'`
   - `properties.status = 'pending'`
3. 遍历每个触发器：
   - 解析触发时间（ISO格式）
   - 比较当前时间与触发时间
   - 如果当前时间 ≥ 触发时间，标记为已触发
4. 更新触发器状态为 `completed`
5. 返回所有已触发的提醒

**代码示例：**
```python
# 检查时间触发器
triggered = await checker.check_time_triggers(
    tenant_id="tenant_001",
    user_id="user_001",
)
# 结果：
# [
#     {
#         "node_id": "node_123",
#         "action": "提醒禹哥面试",
#         "trigger_value": "2026-03-18T10:00:00+08:00",
#         "trigger_type": "time"
#     }
# ]
```

**调用链路：**
- 被调用：定时任务（如每分钟执行一次）
- 调用：
  - `self.graph._ensure_connected()` → 获取Neo4j驱动
  - `session.run()` → 执行Cypher查询
  - `self._update_trigger_status()` → 更新触发器状态

---

### 2. check_event_triggers - 检查事件触发器

```python
async def check_event_triggers(
    self,
    tenant_id: str,
    user_id: str,
    current_query: str,
) -> List[Dict[str, Any]]
```

**功能：** 检查与当前查询匹配的事件触发器。

**参数：**
- `tenant_id`: 租户ID
- `user_id`: 用户ID
- `current_query`: 当前用户查询

**返回值：**
```python
[
    {
        "node_id": str,         # 节点ID
        "action": str,          # 提醒动作
        "trigger_value": str,   # 触发关键词
        "trigger_type": "event" # 触发类型
    },
    ...
]
```

**执行流程：**
1. 查询图谱中所有待处理的事件触发器：
   - `zone = 'procedural'`
   - `'提醒' in tags`
   - `properties.trigger_type = 'event'`
   - `properties.status = 'pending'`
2. 遍历每个触发器：
   - 提取触发关键词（`trigger_value`）
   - 简单关键词匹配（不区分大小写）：
     - 触发词在查询中 OR 查询在触发词中
3. 如果匹配成功，标记为已触发
4. 更新触发器状态为 `completed`
5. 返回所有已触发的提醒

**代码示例：**
```python
# 检查事件触发器
triggered = await checker.check_event_triggers(
    tenant_id="tenant_001",
    user_id="user_001",
    current_query="我要去面试了",
)
# 结果：
# [
#     {
#         "node_id": "node_456",
#         "action": "提醒禹哥带简历",
#         "trigger_value": "面试",
#         "trigger_type": "event"
#     }
# ]
```

**调用链路：**
- 被调用：每次用户查询时（API层）
- 调用：
  - `self.graph._ensure_connected()` → 获取Neo4j驱动
  - `session.run()` → 执行Cypher查询
  - `self._update_trigger_status()` → 更新触发器状态

---

### 3. _update_trigger_status - 更新触发器状态（内部方法）

```python
async def _update_trigger_status(self, node_id: str, new_status: str) -> None
```

**功能：** 更新触发器节点的状态。

**参数：**
- `node_id`: 节点ID
- `new_status`: 新状态（如 `completed`、`expired`）

**执行流程：**
1. 尝试使用APOC函数更新JSON属性：
   ```cypher
   MATCH (n:MemoryNode {id: $node_id})
   SET n.properties = apoc.convert.toJson(
       apoc.convert.fromJsonMap(n.properties) + {status: $new_status}
   )
   ```
2. 如果APOC不可用，回退到手动JSON更新：
   - 查询当前属性
   - 解析JSON
   - 更新 `status` 字段
   - 重新序列化并写回

**调用链路：**
- 被调用：`check_time_triggers()`、`check_event_triggers()`
- 调用：
  - `self.graph._ensure_connected()` → 获取Neo4j驱动
  - `session.run()` → 执行Cypher查询

---

## 调用链路总览

```
定时任务（每分钟）
    ↓
ProspectiveChecker.check_time_triggers()
    ↓
    ├─→ Neo4j查询（查找待处理的时间触发器）
    ├─→ 时间比较（当前时间 vs 触发时间）
    └─→ _update_trigger_status() → 更新状态为completed

用户查询（API层）
    ↓
ProspectiveChecker.check_event_triggers()
    ↓
    ├─→ Neo4j查询（查找待处理的事件触发器）
    ├─→ 关键词匹配（查询 vs 触发词）
    └─→ _update_trigger_status() → 更新状态为completed
```

---

## 关键逻辑说明

### 1. 时间触发器的时区处理
```python
# 获取北京时间（UTC+8）
beijing_tz = timezone(timedelta(hours=8))
current_time = datetime.now(beijing_tz)

# 解析触发时间（确保时区一致）
trigger_time = datetime.fromisoformat(trigger_value.replace("+08:00", ""))
if trigger_time.tzinfo is None:
    trigger_time = trigger_time.replace(tzinfo=beijing_tz)

# 比较时间
if current_time >= trigger_time:
    # 触发！
```

**注意事项：**
- 所有时间比较都在北京时区（UTC+8）进行
- 触发时间存储为ISO格式字符串（如 `2026-03-18T10:00:00+08:00`）

### 2. 事件触发器的关键词匹配
```python
# 简单关键词匹配（不区分大小写）
query_lower = current_query.lower()
trigger_lower = trigger_value.lower()

if trigger_lower in query_lower or query_lower in trigger_lower:
    # 匹配成功！
```

**匹配策略：**
- 双向子串匹配（触发词在查询中 OR 查询在触发词中）
- 不区分大小写
- 未来可扩展为更复杂的语义匹配（如使用LLM）

### 3. 触发器状态更新（APOC回退机制）
```python
# 优先使用APOC（高效）
try:
    await session.run("""
        MATCH (n:MemoryNode {id: $node_id})
        SET n.properties = apoc.convert.toJson(
            apoc.convert.fromJsonMap(n.properties) + {status: $new_status}
        )
    """, node_id=node_id, new_status=new_status)
except Exception:
    # APOC不可用，手动更新JSON
    result = await session.run(
        "MATCH (n:MemoryNode {id: $node_id}) RETURN n.properties as props",
        node_id=node_id
    )
    record = await result.single()
    props = json.loads(record["props"])
    props["status"] = new_status
    await session.run(
        "MATCH (n:MemoryNode {id: $node_id}) SET n.properties = $props",
        node_id=node_id, props=json.dumps(props)
    )
```

**设计理由：**
- APOC插件提供高效的JSON操作
- 如果APOC不可用（如某些Neo4j部署），回退到手动JSON解析

---

## 使用场景

### 场景1：时间提醒（定时任务）
```python
# 每分钟执行一次
async def check_reminders():
    triggered = await checker.check_time_triggers(
        tenant_id="tenant_001",
        user_id="user_001",
    )
    for reminder in triggered:
        # 发送通知给用户
        await send_notification(
            user_id="user_001",
            message=f"提醒：{reminder['action']}"
        )
```

### 场景2：事件提醒（用户查询时）
```python
# 用户发送消息时
async def handle_user_query(query: str):
    # 检查事件触发器
    triggered = await checker.check_event_triggers(
        tenant_id="tenant_001",
        user_id="user_001",
        current_query=query,
    )
    if triggered:
        # 在回复中插入提醒
        reminders = [r['action'] for r in triggered]
        return f"提醒：{', '.join(reminders)}\n\n{normal_response}"
```

---

## 图谱节点结构

### 提醒节点示例
```python
{
    "id": "node_123",
    "name": "面试提醒",
    "zone": "procedural",
    "tags": ["提醒", "面试"],
    "properties": {
        "trigger_type": "time",  # 或 "event"
        "trigger_value": "2026-03-18T10:00:00+08:00",  # 时间或关键词
        "action": "提醒禹哥面试",
        "status": "pending"  # pending / completed / expired
    }
}
```

---

## 注意事项

1. **时区一致性：** 所有时间比较都在北京时区（UTC+8）进行
2. **状态管理：** 触发后立即更新状态为 `completed`，避免重复触发
3. **关键词匹配：** 当前为简单子串匹配，未来可扩展为语义匹配
4. **APOC依赖：** 优先使用APOC，但有回退机制
5. **错误处理：** 解析失败的触发器会被跳过并记录警告

---

## 依赖关系

- **依赖：** `GraphStore`（图谱存储）
- **被依赖：** 定时任务、API层（用户查询处理）
