# buffer.py - 短期记忆缓冲区

## 文件整体功能

`buffer.py` 实现了基于 SQLite 的短期记忆缓冲区，用于存储编码器（encoder）产生的原始记忆单元（memory units），在它们被整合到 Neo4j 长期知识图谱之前提供临时存储。

**核心职责：**
- 提供 SQLite 数据库的 CRUD 操作
- 按会话（session）、日期（date）、租户/用户（tenant/user）维度查询记忆
- 支持记忆归档（archived）标记，用于区分已整合和未整合的记忆
- 支持向量嵌入（embedding）存储（v3.1 新增）

---

## 类：EncoderBuffer

### 作用
SQLite 支持的短期记忆缓冲区，存储原始记忆单元，等待后续整合到长期图谱。

### 初始化

```python
def __init__(self, db_path: str) -> None
```

**参数：**
- `db_path` (str): SQLite 数据库文件路径，父目录会自动创建

**功能：**
1. 创建数据库文件所在目录（如不存在）
2. 调用 `_init_db()` 初始化数据库表结构

**调用链路：**
- 被：服务启动时实例化
- 调用：`_init_db()`

---

## 核心方法

### 1. write() - 写入记忆单元

```python
def write(
    self,
    tenant_id: str,
    user_id: str,
    session_id: str,
    memory_unit: Dict[str, Any],
) -> str
```

**功能：**
将一个记忆单元写入缓冲区。

**参数：**
- `tenant_id`: 租户标识
- `user_id`: 用户标识
- `session_id`: 会话标识
- `memory_unit`: 记忆单元字典（包含 id、timestamp、importance 等字段）

**返回值：**
- 写入的记忆单元 ID（如果 memory_unit 中没有 id，会自动生成 UUID）

**关键逻辑：**
1. 自动补全 `id`（UUID）和 `timestamp`（UTC 时间）
2. 提取日期字符串（YYYY-MM-DD）用于索引
3. 将整个 memory_unit 序列化为 JSON 存入 `data` 字段
4. 使用 `INSERT OR REPLACE` 支持幂等写入

**调用链路：**
- 被：编码器（encoder）在处理对话后调用
- 调用：`_conn()` 上下文管理器

**代码示例：**
```python
buffer = EncoderBuffer("/path/to/buffer.db")
unit_id = buffer.write(
    tenant_id="tenant1",
    user_id="user1",
    session_id="session123",
    memory_unit={
        "type": "memory",
        "content": "用户提到了减肥计划",
        "importance": 0.8,
    }
)
```

---

### 2. read_by_session() - 按会话读取

```python
def read_by_session(self, session_id: str) -> List[Dict[str, Any]]
```

**功能：**
读取指定会话的所有记忆单元，按时间戳升序排列。

**参数：**
- `session_id`: 会话标识

**返回值：**
- 记忆单元字典列表

**调用链路：**
- 被：会话上下文加载时调用
- 调用：`_conn()`, `_row_to_unit()`

---

### 3. read_by_date() - 按日期读取

```python
def read_by_date(self, tenant_id: str, user_id: str, date: str) -> List[Dict[str, Any]]
```

**功能：**
读取指定日期（YYYY-MM-DD）的所有记忆单元。

**参数：**
- `tenant_id`: 租户标识
- `user_id`: 用户标识
- `date`: 日期字符串（格式：YYYY-MM-DD）

**返回值：**
- 记忆单元字典列表，按时间戳升序

**调用链路：**
- 被：每日记忆整合任务调用
- 调用：`_conn()`, `_row_to_unit()`

---

### 4. read_recent() - 读取最近记忆

```python
def read_recent(
    self, tenant_id: str, user_id: str, limit: int = 20
) -> List[Dict[str, Any]]
```

**功能：**
读取租户/用户的最近 N 条记忆单元。

**参数：**
- `tenant_id`: 租户标识
- `user_id`: 用户标识
- `limit`: 返回数量上限（默认 20）

**返回值：**
- 记忆单元字典列表，最新的在前

**调用链路：**
- 被：上下文召回时调用
- 调用：`_conn()`, `_row_to_unit()`

---

### 5. archive() - 归档记忆

```python
def archive(self, tenant_id: str, user_id: str, date: str) -> None
```

**功能：**
将指定日期的所有记忆单元标记为已归档（archived=1），表示已整合到长期图谱。

**参数：**
- `tenant_id`: 租户标识
- `user_id`: 用户标识
- `date`: 日期字符串（YYYY-MM-DD）

**调用链路：**
- 被：每日整合任务完成后调用
- 调用：`_conn()`

**关键逻辑：**
- 归档后的记忆不会被 `read_unarchived()` 返回
- 归档是单向操作，不可逆

---

### 6. read_unarchived() - 读取未归档记忆

```python
def read_unarchived(self, tenant_id: str, user_id: str) -> List[Dict[str, Any]]
```

**功能：**
读取所有未归档的记忆单元，按时间戳升序。

**参数：**
- `tenant_id`: 租户标识
- `user_id`: 用户标识

**返回值：**
- 未归档记忆单元列表

**调用链路：**
- 被：整合任务启动时调用，获取待处理记忆
- 调用：`_conn()`, `_row_to_unit()`

---

### 7. get_latest_session_summary() - 获取最新会话摘要

```python
def get_latest_session_summary(
    self, tenant_id: str, user_id: str
) -> Optional[Dict[str, Any]]
```

**功能：**
获取租户/用户的最新会话摘要（type='session_summary'）。

**参数：**
- `tenant_id`: 租户标识
- `user_id`: 用户标识

**返回值：**
- 最新会话摘要字典，如果不存在则返回 None

**调用链路：**
- 被：上下文加载时调用，用于快速获取最近会话概要
- 调用：`_conn()`, `_row_to_unit()`

---

## 向量嵌入支持（v3.1 新增）

### 8. update_embedding() - 更新嵌入向量

```python
def update_embedding(self, unit_id: str, embedding_bytes: bytes) -> None
```

**功能：**
为指定记忆单元存储向量嵌入（二进制格式）。

**参数：**
- `unit_id`: 记忆单元 ID
- `embedding_bytes`: 嵌入向量的二进制表示

**调用链路：**
- 被：嵌入生成任务调用
- 调用：`_conn()`

---

### 9. get_embeddings() - 获取所有嵌入

```python
def get_embeddings(self, tenant_id: str, user_id: str) -> list
```

**功能：**
获取所有未归档且有嵌入向量的记忆单元。

**参数：**
- `tenant_id`: 租户标识
- `user_id`: 用户标识

**返回值：**
- `[(unit_id, embedding_bytes), ...]` 列表

**调用链路：**
- 被：向量检索任务调用
- 调用：`_conn()`

---

## 内部辅助方法

### _conn() - 数据库连接上下文管理器

```python
@contextmanager
def _conn(self) -> Generator[sqlite3.Connection, None, None]
```

**功能：**
提供带自动提交/回滚的 SQLite 连接上下文。

**关键逻辑：**
- 设置 `row_factory = sqlite3.Row`，支持字典式访问
- 自动提交成功的事务
- 异常时自动回滚
- 确保连接关闭

---

### _init_db() - 初始化数据库

```python
def _init_db(self) -> None
```

**功能：**
创建表和索引（如果不存在）。

**表结构：**
```sql
CREATE TABLE IF NOT EXISTS memory_buffer (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL DEFAULT 'memory',
    tenant_id   TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    session_id  TEXT NOT NULL,
    data        TEXT NOT NULL,   -- JSON blob
    importance  REAL NOT NULL DEFAULT 0.0,
    timestamp   TEXT NOT NULL,
    archived    INTEGER NOT NULL DEFAULT 0,
    date        TEXT NOT NULL,   -- YYYY-MM-DD
    embedding   BLOB             -- v3.1 新增
);
```

**索引：**
- `idx_session`: session_id
- `idx_tenant_user`: (tenant_id, user_id)
- `idx_date`: (tenant_id, user_id, date)
- `idx_archived`: (tenant_id, user_id, archived)

**迁移逻辑：**
- 检测 `embedding` 列是否存在，不存在则添加（v3.1 兼容性）

---

### _row_to_unit() - 行转记忆单元

```python
@staticmethod
def _row_to_unit(row: sqlite3.Row) -> Dict[str, Any]
```

**功能：**
将数据库行反序列化为记忆单元字典。

**关键逻辑：**
1. 从 `data` 字段解析 JSON
2. 将 `archived` 字段（0/1）转换为布尔值
3. 返回完整的记忆单元字典

---

## 调用链路总览

```
服务启动
  → EncoderBuffer.__init__()
    → _init_db()

编码器处理对话
  → write()
    → _conn()

上下文加载
  → read_by_session() / read_recent() / get_latest_session_summary()
    → _conn()
    → _row_to_unit()

每日整合任务
  → read_by_date() / read_unarchived()
    → _conn()
    → _row_to_unit()
  → [整合到 Neo4j]
  → archive()
    → _conn()

向量检索
  → get_embeddings()
    → _conn()
```

---

## 重要注意事项

1. **幂等写入**：使用 `INSERT OR REPLACE`，相同 ID 的记忆单元会被覆盖
2. **时区处理**：所有时间戳使用 UTC（`datetime.utcnow()`）
3. **JSON 序列化**：整个 memory_unit 存储在 `data` 字段，确保 `ensure_ascii=False` 支持中文
4. **归档不可逆**：一旦标记为 archived，无法恢复为未归档状态
5. **向量嵌入**：v3.1 新增功能，需要确保数据库迁移正确执行
6. **多租户隔离**：所有查询都必须指定 tenant_id 和 user_id，确保数据隔离

---

## 性能优化建议

1. **索引覆盖**：常用查询已有索引覆盖（session_id, date, archived）
2. **批量写入**：如需批量写入，考虑使用事务包裹多个 write() 调用
3. **定期清理**：归档后的旧记忆可定期清理，避免数据库膨胀
4. **嵌入存储**：embedding 字段使用 BLOB 类型，适合存储二进制向量数据
