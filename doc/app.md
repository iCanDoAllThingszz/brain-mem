# app.py - Brain Memory Service 主应用

## 文件整体功能

`app.py` 是 Brain Memory Service 的核心入口文件，基于 FastAPI 框架构建。它负责：

1. **服务生命周期管理**：初始化所有组件（存储、引擎、工作记忆等）
2. **HTTP API 端点**：提供会话管理、记忆检索、巩固等 RESTful 接口
3. **后台任务调度**：异步处理记忆编码、会话总结、巩固等耗时操作
4. **全局异常处理**：统一错误响应格式

---

## 核心组件

### 1. 生命周期管理器 `lifespan`

**功能**：FastAPI 应用启动和关闭时的初始化/清理逻辑

**流程**：
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    1. 加载 config.yaml 配置
    2. 配置 LLM 客户端（base_url, model, api_key）
    3. 初始化存储层：
       - GraphStore（Neo4j 图数据库）
       - TagDict（标签字典，JSON 文件）
       - EncoderBuffer（编码缓冲区，SQLite）
    4. 初始化引擎层：
       - Perceiver（感知器）
       - Evaluator（评估器）
       - Encoder（编码器）
       - Retriever（检索器）
       - Consolidator（巩固器）
       - WorkingMemory（工作记忆）
       - ProspectiveChecker（前瞻记忆检查器）
    5. 预置种子标签（人物、组织、地点等）
    6. 确保向量索引存在
    
    yield  # 应用运行
    
    # 关闭时
    7. 关闭 GraphStore 连接
```

**关键配置**：
- Neo4j 连接：`bolt://localhost:7687`（默认）
- 数据目录：`./data/`
- 种子标签：17 个预定义类别（人物、组织、地点、物品、作品、概念、技能等）

---

### 2. 请求/响应模型

#### BaseRequest
```python
class BaseRequest(BaseModel):
    tenant_id: str    # 租户 ID（多租户隔离）
    user_id: str      # 用户 ID
    session_id: str   # 会话 ID
```

#### SessionStartRequest
```python
class SessionStartRequest(BaseRequest):
    user_profile: Optional[dict] = None    # 用户画像
    agent_context: Optional[dict] = None   # Agent 上下文
```

#### BeforeQueryRequest
```python
class BeforeQueryRequest(BaseRequest):
    query: str                              # 用户查询
    recent_messages: Optional[list] = None  # 近期消息
```

#### AfterResponseRequest
```python
class AfterResponseRequest(BaseRequest):
    user_message: str         # 用户消息
    assistant_response: str   # 助手回复
```

#### SessionEndRequest
```python
class SessionEndRequest(BaseRequest):
    conversation_history: list  # 完整对话历史
```

---

## API 端点

### 1. `/health` (GET)
**功能**：健康检查

**返回**：
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

---

### 2. `/logs` (GET)
**功能**：查看最近的活动日志

**参数**：
- `n` (int, 默认 30)：返回最近 N 条日志

**返回**：
```json
{
  "logs": "格式化的日志文本"
}
```

**调用链路**：
- `get_logs()` → `activity_log.read_recent(n)`

---

### 3. `/hooks/session-start` (POST)
**功能**：会话开始钩子，加载工作记忆并检查时间触发的前瞻记忆

**请求体**：`SessionStartRequest`

**流程**：
```
1. 调用 ProspectiveChecker.check_time_triggers() 检查时间触发器
2. 调用 WorkingMemory.load() 加载工作记忆
3. 合并触发的提醒到 pending_reminders
4. 记录日志
5. 返回上下文和待办提醒
```

**返回**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "context": "工作记忆上下文文本",
    "pending_reminders": ["提醒1", "提醒2"]
  }
}
```

**调用链路**：
- `session_start()` → `ProspectiveChecker.check_time_triggers()` → `WorkingMemory.load()` → `log_event()`

---

### 4. `/hooks/before-query` (POST)
**功能**：查询前钩子，检索相关记忆并检查事件触发的前瞻记忆

**请求体**：`BeforeQueryRequest`

**流程**：
```
1. 调用 ProspectiveChecker.check_event_triggers() 检查事件触发器
2. 从 WorkingMemory 获取当前会话的工作记忆
3. 调用 Retriever.retrieve() 检索相关记忆
4. 如果有触发的提醒，注入到上下文中
5. 记录日志
6. 返回增强后的上下文
```

**返回**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "context": "检索到的记忆上下文 + 触发的提醒"
  }
}
```

**调用链路**：
- `before_query()` → `ProspectiveChecker.check_event_triggers()` → `WorkingMemory.get()` → `Retriever.retrieve()` → `log_event()`

---

### 5. `/hooks/after-response` (POST)
**功能**：响应后钩子，异步处理用户消息的记忆编码

**请求体**：`AfterResponseRequest`

**流程**：
```
1. 立即返回 {"status": "accepted"}
2. 后台任务 _process_after_response() 执行：
   a. 增加会话消息计数
   b. 每 10 条消息触发一次中间总结
   c. 调用 Perceiver.classify() 分类消息
   d. 如果是 informative 类型：
      - 调用 Evaluator.evaluate() 评估记忆价值
      - 如果决定编码，调用 Encoder.encode_message()
   e. 记录日志
```

**返回**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "accepted"
  }
}
```

**调用链路**：
- `after_response()` → `BackgroundTasks.add_task(_process_after_response)` → `Perceiver.classify()` → `Evaluator.evaluate()` → `Encoder.encode_message()` → `log_event()`

**关键逻辑**：
- **中间总结机制**：每 10 条消息自动生成会话总结，避免等到会话结束才总结
- **分类驱动编码**：只有 `informative` 类型的消息才进入评估和编码流程
- **自动通过类别**：`log_*`、`reconsolidation`、`prospective`、`forget` 类别绕过评估器，直接编码

---

### 6. `/hooks/session-end` (POST)
**功能**：会话结束钩子，生成会话总结并清理工作记忆

**请求体**：`SessionEndRequest`

**流程**：
```
1. 立即返回 {"status": "accepted"}
2. 后台任务 _process_session_end() 执行：
   a. 调用 Encoder.generate_session_summary() 生成总结
   b. 调用 WorkingMemory.destroy() 清理会话
   c. 清理会话消息计数器
```

**返回**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "accepted",
    "task_id": "uuid"
  }
}
```

**调用链路**：
- `session_end()` → `BackgroundTasks.add_task(_process_session_end)` → `Encoder.generate_session_summary()` → `WorkingMemory.destroy()`

---

### 7. `/hooks/consolidate` (POST)
**功能**：触发记忆巩固（将缓冲区记忆写入图数据库）

**请求体**：`ConsolidateRequest`

**流程**：
```
1. 生成任务 ID
2. 立即返回 {"status": "accepted", "task_id": "..."}
3. 后台任务 _process_consolidate() 执行：
   a. 调用 Consolidator.consolidate()
   b. 记录巩固结果日志
```

**返回**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "status": "accepted",
    "task_id": "uuid"
  }
}
```

**调用链路**：
- `consolidate()` → `BackgroundTasks.add_task(_process_consolidate)` → `Consolidator.consolidate()` → `log_event()`

---

### 8. `/hooks/check-prospective` (POST)
**功能**：检查时间触发的前瞻记忆（可由外部 cron 调用）

**请求体**：`CheckProspectiveRequest`

**流程**：
```
1. 调用 ProspectiveChecker.check_time_triggers()
2. 记录触发的提醒日志
3. 返回触发的提醒列表
```

**返回**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "triggered_count": 2,
    "reminders": [
      {"action": "提醒交报告", "trigger_value": "2026-03-15T09:00:00+08:00"},
      {"action": "提醒记录饮食", "trigger_value": "2026-03-16T08:00:00+08:00"}
    ]
  }
}
```

**调用链路**：
- `check_prospective()` → `ProspectiveChecker.check_time_triggers()` → `log_event()`

---

### 9. `/hooks/backfill-embeddings` (POST)
**功能**：一次性回填所有缺失嵌入向量的节点

**请求体**：
```json
{
  "tenant_id": "default",
  "user_id": "yugo"
}
```

**流程**：
```
1. 调用 GraphStore.find_nodes_without_embedding() 查找缺失嵌入的节点
2. 批量生成嵌入向量
3. 更新节点嵌入
4. 记录日志
```

**返回**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "backfilled": 42,
    "total": 50
  }
}
```

**调用链路**：
- `backfill_embeddings()` → `GraphStore.find_nodes_without_embedding()` → `get_embeddings()` → `GraphStore.update_node_embedding()` → `log_event()`

---

## 后台任务函数

### `_process_after_response()`
**功能**：异步处理用户消息的记忆编码

**参数**：
- `user_message` (str)：用户消息
- `tenant_id`, `user_id`, `session_id` (str)：标识符
- `perceiver`, `evaluator`, `encoder` (对象)：引擎组件
- `wm_store` (WorkingMemory)：工作记忆存储

**流程**：
```
1. 增加会话消息计数
2. 每 10 条消息触发中间总结
3. 获取工作记忆
4. 调用 Perceiver.classify() 分类
5. 如果是 informative：
   a. 使用 rewrite（如果有）或原始消息
   b. 对于特殊类别（log_*, reconsolidation, prospective, forget）：
      - 自动通过评估，直接编码
   c. 对于其他类别：
      - 调用 Evaluator.evaluate()
   d. 如果决定编码：
      - 调用 Encoder.encode_message()
      - 记录日志
```

**关键逻辑**：
- **中间总结**：避免长会话丢失上下文
- **重写优先**：使用 Perceiver 的高密度重写而非原始消息
- **分类驱动**：不同类别走不同编码路径

---

### `_process_session_end()`
**功能**：生成会话总结并清理工作记忆

**参数**：
- `conversation_history` (list)：对话历史
- `tenant_id`, `user_id`, `session_id` (str)：标识符
- `encoder` (Encoder)：编码器
- `wm_store` (WorkingMemory)：工作记忆存储

**流程**：
```
1. 调用 Encoder.generate_session_summary()
2. 调用 WorkingMemory.destroy()
3. 清理会话消息计数器
```

---

### `_process_consolidate()`
**功能**：执行记忆巩固

**参数**：
- `tenant_id`, `user_id` (str)：标识符
- `consolidator` (Consolidator)：巩固器

**流程**：
```
1. 调用 Consolidator.consolidate()
2. 记录巩固结果日志（节点创建/更新/合并数、关系数、模式、冲突）
```

---

## 全局状态

### `_session_msg_counts`
**类型**：`Dict[str, int]`

**功能**：跟踪每个会话的消息计数，用于触发中间总结

**更新时机**：每次 `_process_after_response()` 调用时 +1

**清理时机**：会话结束时删除

---

### `_SESSION_SUMMARY_INTERVAL`
**类型**：`int`

**值**：10

**功能**：每 N 条消息触发一次中间总结

---

## 异常处理

### `global_exception_handler`
**功能**：捕获所有未处理的异常，返回统一的 500 错误响应

**返回**：
```json
{
  "code": 500,
  "message": "异常信息",
  "data": null
}
```

---

## 辅助函数

### `ok(data: Any) -> dict`
**功能**：构造成功响应

**返回**：
```json
{
  "code": 0,
  "message": "success",
  "data": <data>
}
```

---

### `err(code: int, message: str) -> dict`
**功能**：构造错误响应

**返回**：
```json
{
  "code": <code>,
  "message": <message>,
  "data": null
}
```

---

## 调用关系图

```
app.py
├── lifespan()
│   ├── GraphStore.connect()
│   ├── GraphStore.ensure_vector_index()
│   └── TagDict.add_tag()
│
├── /health
│
├── /logs
│   └── activity_log.read_recent()
│
├── /hooks/session-start
│   ├── ProspectiveChecker.check_time_triggers()
│   ├── WorkingMemory.load()
│   └── log_event()
│
├── /hooks/before-query
│   ├── ProspectiveChecker.check_event_triggers()
│   ├── WorkingMemory.get()
│   ├── Retriever.retrieve()
│   └── log_event()
│
├── /hooks/after-response
│   └── BackgroundTasks → _process_after_response()
│       ├── Perceiver.classify()
│       ├── Evaluator.evaluate()
│       ├── Encoder.encode_message()
│       └── log_event()
│
├── /hooks/session-end
│   └── BackgroundTasks → _process_session_end()
│       ├── Encoder.generate_session_summary()
│       └── WorkingMemory.destroy()
│
├── /hooks/consolidate
│   └── BackgroundTasks → _process_consolidate()
│       ├── Consolidator.consolidate()
│       └── log_event()
│
├── /hooks/check-prospective
│   ├── ProspectiveChecker.check_time_triggers()
│   └── log_event()
│
└── /hooks/backfill-embeddings
    ├── GraphStore.find_nodes_without_embedding()
    ├── get_embeddings()
    ├── GraphStore.update_node_embedding()
    └── log_event()
```

---

## 重要注意事项

1. **多租户隔离**：所有操作都需要 `tenant_id` 和 `user_id`，确保数据隔离
2. **异步处理**：编码、总结、巩固等耗时操作都在后台任务中执行，避免阻塞 API 响应
3. **中间总结机制**：每 10 条消息自动生成总结，防止长会话丢失上下文
4. **前瞻记忆**：支持时间触发和事件触发两种提醒机制
5. **日志记录**：所有关键操作都通过 `activity_log.log_event()` 记录，便于调试和审计
6. **向量索引**：启动时自动确保 Neo4j 向量索引存在，支持语义检索
7. **种子标签**：预置 17 个常用标签，避免冷启动问题
8. **错误容错**：向量索引创建失败不会阻止服务启动，只记录警告
