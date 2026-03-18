# activity_log.py - 活动日志记录器

## 文件整体功能

`activity_log.py` 是 Brain Memory Service 的结构化日志系统，负责记录所有关键操作的活动日志。它提供：

1. **结构化日志记录**：将事件以 JSON 格式写入日志文件
2. **自动日志轮转**：保持最近 500 条日志，自动清理旧日志
3. **北京时间戳**：所有日志使用北京时间（UTC+8）
4. **日志查询**：支持读取最近 N 条日志并格式化输出

---

## 核心常量

### `_LOG_DIR`
**类型**：`str`

**值**：`<项目根目录>/data`

**功能**：日志文件存储目录

---

### `_LOG_FILE`
**类型**：`str`

**值**：`<项目根目录>/data/activity.log`

**功能**：日志文件完整路径

---

### `_MAX_LINES`
**类型**：`int`

**值**：500

**功能**：日志文件最大行数，超过后自动裁剪

---

### `_BJT`
**类型**：`timezone`

**值**：`timezone(timedelta(hours=8))`

**功能**：北京时区对象（UTC+8）

---

## 核心函数

### 1. `_now_bjt() -> str`

**功能**：获取当前北京时间的格式化字符串

**返回**：
- 格式：`"YYYY-MM-DD HH:MM:SS"`
- 示例：`"2026-03-17 14:30:45"`

**实现**：
```python
def _now_bjt() -> str:
    return datetime.now(_BJT).strftime("%Y-%m-%d %H:%M:%S")
```

**调用链路**：
- `log_event()` → `_now_bjt()`

---

### 2. `_ensure_dir()`

**功能**：确保日志目录存在，不存在则创建

**实现**：
```python
def _ensure_dir():
    os.makedirs(_LOG_DIR, exist_ok=True)
```

**调用链路**：
- `log_event()` → `_ensure_dir()`

---

### 3. `log_event(event_type: str, summary: str, details: Optional[Dict[str, Any]] = None) -> None`

**功能**：记录一条结构化日志

**参数**：
- `event_type` (str)：事件类型，可选值：
  - `hook_session_start`：会话开始
  - `hook_before_query`：查询前
  - `hook_after_response`：响应后
  - `hook_session_end`：会话结束
  - `hook_consolidate`：巩固
  - `perceiver`：感知器分类
  - `evaluator`：评估器评估
  - `encoder`：编码器编码
  - `retriever`：检索器检索
  - `working_memory`：工作记忆操作
  - `prospective_trigger`：前瞻记忆触发
  - `intermediate_summary`：中间总结
  - `backfill`：嵌入回填
  - `error`：错误
- `summary` (str)：事件摘要（最多 200 字符）
- `details` (Optional[Dict[str, Any]])：事件详细信息（可选）

**流程**：
```
1. 确保日志目录存在
2. 构造日志条目：
   {
     "time": "北京时间",
     "type": "事件类型",
     "summary": "摘要（截断到200字符）",
     "details": {清理后的详细信息}
   }
3. 清理 details：
   - 字符串超过 300 字符截断
   - 列表超过 10 项截断
4. 将日志条目序列化为 JSON 并追加到文件
5. 调用 _trim_log() 裁剪日志
```

**详细信息清理规则**：
- 字符串值：超过 300 字符截断，添加 `"..."`
- 列表值：超过 10 项截断
- 其他类型：保持原样

**示例**：
```python
log_event("perceiver", "[informative] 赵禹询问AI Agent最新动态", {
    "type": "informative",
    "category": "cognition",
    "rewrite": "赵禹询问AI Agent最新动态，表明他持续关注AI Agent领域",
})
```

**生成的日志条目**：
```json
{
  "time": "2026-03-17 14:30:45",
  "type": "perceiver",
  "summary": "[informative] 赵禹询问AI Agent最新动态",
  "details": {
    "type": "informative",
    "category": "cognition",
    "rewrite": "赵禹询问AI Agent最新动态，表明他持续关注AI Agent领域"
  }
}
```

**调用链路**：
- `app.py` 各端点 → `log_event()`
- `log_event()` → `_ensure_dir()` → `_trim_log()`

---

### 4. `_trim_log()`

**功能**：裁剪日志文件，保持最近 `_MAX_LINES` 条日志

**流程**：
```
1. 读取日志文件所有行
2. 如果行数超过 _MAX_LINES：
   - 保留最后 _MAX_LINES 行
   - 重写日志文件
3. 忽略所有异常（静默失败）
```

**实现**：
```python
def _trim_log():
    try:
        with open(_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > _MAX_LINES:
            with open(_LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-_MAX_LINES:])
    except Exception:
        pass
```

**调用链路**：
- `log_event()` → `_trim_log()`

---

### 5. `read_recent(n: int = 30) -> str`

**功能**：读取最近 N 条日志并格式化为可读文本

**参数**：
- `n` (int, 默认 30)：返回最近 N 条日志

**返回**：
- 格式化的日志文本，每行格式：
  ```
  [时间] 事件类型: 摘要 | key1=value1, key2=value2
  ```
- 如果日志文件不存在，返回 `"No activity log yet."`

**流程**：
```
1. 读取日志文件最后 N 行
2. 对每行：
   a. 解析 JSON
   b. 提取 time, type, summary, details
   c. 格式化 details（排除 context 字段，最多显示 5 个键值对）
   d. 拼接为可读文本
3. 返回拼接后的文本
```

**示例输出**：
```
[2026-03-17 14:30:45] perceiver: [informative] 赵禹询问AI Agent最新动态 | type=informative, category=cognition
[2026-03-17 14:30:46] evaluator: relevance=7 emotion=0 novelty=6 | encode_decision=True, encode_priority=high
[2026-03-17 14:30:47] encoder: Encoded: 赵禹询问AI Agent最新动态 | importance=7.2, entities=['赵禹(update)', 'AI Agent(create)']
```

**调用链路**：
- `app.py` `/logs` 端点 → `read_recent()`

---

## 日志条目结构

### 标准格式
```json
{
  "time": "YYYY-MM-DD HH:MM:SS",
  "type": "事件类型",
  "summary": "事件摘要（最多200字符）",
  "details": {
    "key1": "value1",
    "key2": "value2"
  }
}
```

### 常见事件类型及其 details

#### 1. `hook_session_start`
```json
{
  "goals": ["目标1", "目标2"],
  "reminders": ["提醒1"],
  "emotional_baseline": "neutral",
  "context": "工作记忆上下文（截断到200字符）",
  "triggered_time_reminders": 2
}
```

#### 2. `hook_before_query`
```json
{
  "memories_found": 5,
  "top_memories": [
    "记忆1内容（截断到60字符） (score=0.85)",
    "记忆2内容 (score=0.78)"
  ],
  "triggered_reminders": 1
}
```

#### 3. `perceiver`
```json
{
  "type": "informative",
  "category": "cognition",
  "target_entity": "减肥计划",
  "reason": "分类原因",
  "rewrite": "重写后的高密度陈述（截断到100字符）"
}
```

#### 4. `evaluator`
```json
{
  "encode_decision": true,
  "encode_priority": "high",
  "reason": "评估原因"
}
```

#### 5. `encoder`
```json
{
  "importance": 7.2,
  "entities": ["赵禹(update)", "AI Agent(create)", "跳槽计划(update)"],
  "relations": 3
}
```

或（跳过编码时）：
```json
{
  "reason": "semantic_duplicate"
}
```

#### 6. `consolidation`
```json
{
  "nodes_created": 5,
  "nodes_updated": 3,
  "nodes_merged": 2,
  "relations_created": 8,
  "patterns": ["模式1", "模式2"],
  "conflicts": ["冲突1"]
}
```

#### 7. `prospective_trigger`
```json
{
  "triggers": ["提醒交报告", "提醒记录饮食"]
}
```

#### 8. `intermediate_summary`
```json
{
  "session_id": "uuid",
  "message_count": 10
}
```

#### 9. `backfill`
```json
{}
```

---

## 调用关系图

```
activity_log.py
├── log_event()
│   ├── _now_bjt()
│   ├── _ensure_dir()
│   └── _trim_log()
│
└── read_recent()
```

**被调用者**：
```
app.py
├── session_start() → log_event("hook_session_start", ...)
├── before_query() → log_event("hook_before_query", ...)
├── _process_after_response()
│   ├── log_event("perceiver", ...)
│   ├── log_event("evaluator", ...)
│   ├── log_event("encoder", ...)
│   └── log_event("intermediate_summary", ...)
├── _process_consolidate() → log_event("consolidation", ...)
├── check_prospective() → log_event("prospective_trigger", ...)
├── backfill_embeddings() → log_event("backfill", ...)
└── get_logs() → read_recent()
```

---

## 重要注意事项

1. **时区一致性**：所有日志使用北京时间（UTC+8），与服务器时区（UTC）不同
2. **自动裁剪**：日志文件自动保持最近 500 条，避免无限增长
3. **静默失败**：所有异常都被捕获并忽略，确保日志记录不会影响主流程
4. **详细信息清理**：自动截断过长的字符串和列表，防止日志文件膨胀
5. **JSON 格式**：每行一个 JSON 对象，便于解析和分析
6. **context 字段排除**：`read_recent()` 格式化时排除 `context` 字段，避免输出过长
7. **编码安全**：使用 UTF-8 编码，支持中文日志
8. **追加写入**：使用 `"a"` 模式追加日志，不会覆盖已有日志
9. **目录自动创建**：首次写入时自动创建 `data/` 目录
10. **无外部依赖**：仅依赖 Python 标准库（`json`, `os`, `datetime`）
