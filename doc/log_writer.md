# log_writer.py - 日志写入器

## 文件整体功能

`LogWriter` 是 brain-memory 服务的日志写入组件，负责将日志类型的信息写入文件系统，并更新图谱索引。

**核心职责：**
- 将日志按类别（饮食、运动、面试、交易、学习等）写入对应的 Markdown 文件
- 更新图谱实体的日志索引属性（`last_log_date`、`log_path`）
- 支持北京时间（UTC+8）的时间戳处理

**设计理念（v3）：**
- 详细日志存储在文件系统（易于人类阅读）
- 高层次认知存储在图谱（易于机器检索）

---

## 类：LogWriter

### 作用
日志写入器，将日志信息写入文件系统并更新图谱实体索引。

### 类属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `BASE_DIR` | str | 日志根目录：`/root/.openclaw/workspace/memory/logs` |
| `CATEGORY_DIRS` | dict | 日志类别到子目录的映射 |

**支持的日志类别：**
```python
{
    "log_diet": "diet",          # 饮食记录
    "log_exercise": "exercise",  # 运动记录
    "log_interview": "interview",# 面试记录
    "log_trading": "trading",    # 交易记录
    "log_learning": "learning",  # 学习记录
    "log_general": "general",    # 通用日志
}
```

### 初始化方法

```python
def __init__(self, graph: GraphStore) -> None
```

**参数：**
- `graph`: GraphStore 实例，用于更新图谱索引

---

## 核心方法

### 1. write_log - 写入日志条目

```python
async def write_log(
    self,
    category: str,
    message: str,
    target_entity: Optional[str],
    tenant_id: str,
    user_id: str,
    timestamp: Optional[datetime] = None,
) -> Dict[str, Any]
```

**功能：** 将日志条目写入文件并更新图谱索引。

**参数：**
- `category`: 日志类别（如 `log_diet`、`log_exercise`）
- `message`: 日志消息内容
- `target_entity`: 要更新的图谱实体名称（如"减肥计划"），可选
- `tenant_id`: 租户ID
- `user_id`: 用户ID
- `timestamp`: 可选时间戳（默认为当前UTC+8时间）

**返回值：**
```python
{
    "file_path": str,              # 日志文件路径
    "log_date": str,               # 日志日期（YYYY-MM-DD）
    "target_entity_updated": bool  # 图谱实体是否更新成功
}
```

**执行流程：**
1. 验证日志类别（未知类别默认为 `log_general`）
2. 转换时间戳为北京时间（UTC+8）
3. 确定日志文件路径：`BASE_DIR/{category_subdir}/{YYYY-MM-DD}.md`
4. 创建目录（如不存在）
5. 追加日志条目到文件：
   - 新文件：写入标题 `# {类别名称} {日期}`
   - 已有文件：直接追加 `- {时间} {消息}`
6. 如果指定了 `target_entity`，更新图谱实体索引

**代码示例：**
```python
# 写入饮食日志
result = await log_writer.write_log(
    category="log_diet",
    message="早餐：燕麦粥 + 鸡蛋（300大卡）",
    target_entity="减肥计划",
    tenant_id="tenant_001",
    user_id="user_001",
)
# 结果：
# {
#     "file_path": "/root/.openclaw/workspace/memory/logs/diet/2026-03-18.md",
#     "log_date": "2026-03-18",
#     "target_entity_updated": True
# }
```

**调用链路：**
- 被调用：API 层（如 `/api/log` 端点）
- 调用：
  - `self._get_category_display_name()` → 获取类别显示名称
  - `self._update_graph_index()` → 更新图谱索引

---

### 2. _update_graph_index - 更新图谱索引（内部方法）

```python
async def _update_graph_index(
    self,
    entity_name: str,
    log_path: str,
    date: str,
    tenant_id: str,
    user_id: str,
) -> bool
```

**功能：** 更新图谱实体的日志索引属性。

**参数：**
- `entity_name`: 实体名称
- `log_path`: 日志目录路径
- `date`: 日志日期（YYYY-MM-DD）
- `tenant_id`: 租户ID
- `user_id`: 用户ID

**返回值：**
- `True`: 实体找到并更新成功
- `False`: 实体未找到或更新失败

**更新的属性：**
```python
{
    "last_log_date": "2026-03-18",  # 最新日志日期
    "log_path": "/root/.openclaw/workspace/memory/logs/diet"  # 日志目录路径
}
```

**执行流程：**
1. 通过名称查找图谱实体：`graph.find_nodes_by_name()`
2. 如果找不到实体，记录警告并返回 `False`
3. 更新第一个匹配节点的属性（合并现有属性）
4. 记录更新日志

**调用链路：**
- 被调用：`write_log()`
- 调用：
  - `self.graph.find_nodes_by_name()` → 查找实体
  - `self.graph.update_node()` → 更新节点

---

### 3. _get_category_display_name - 获取类别显示名称（静态方法）

```python
@staticmethod
def _get_category_display_name(category: str) -> str
```

**功能：** 获取日志类别的中文显示名称。

**参数：**
- `category`: 日志类别（如 `log_diet`）

**返回值：**
- 中文显示名称（如"饮食记录"）

**映射表：**
```python
{
    "log_diet": "饮食记录",
    "log_exercise": "运动记录",
    "log_interview": "面试记录",
    "log_trading": "交易记录",
    "log_learning": "学习记录",
    "log_general": "日志记录",
}
```

---

## 调用链路总览

```
API层（/api/log）
    ↓
LogWriter.write_log()
    ↓
    ├─→ _get_category_display_name() → 获取类别名称
    ├─→ 文件系统写入（追加日志）
    └─→ _update_graph_index()
            ↓
            ├─→ GraphStore.find_nodes_by_name() → 查找实体
            └─→ GraphStore.update_node() → 更新节点属性
```

---

## 关键逻辑说明

### 1. 时区处理（北京时间）
```python
# 转换为北京时间（UTC+8）
from datetime import timedelta
beijing_time = timestamp + timedelta(hours=8)
date_str = beijing_time.strftime("%Y-%m-%d")
time_str = beijing_time.strftime("%H:%M")
```

**注意事项：**
- 所有日志文件名和时间戳都使用北京时间
- 输入的 `timestamp` 应为 UTC 时间
- 如果未提供 `timestamp`，默认使用当前 UTC 时间

### 2. 文件追加逻辑
```python
# 新文件：写入标题
if is_new_file:
    f.write(f"# {category_name} {date_str}\n\n")

# 追加日志条目
f.write(f"- {time_str} {message}\n")
```

**文件格式示例：**
```markdown
# 饮食记录 2026-03-18

- 08:30 早餐：燕麦粥 + 鸡蛋（300大卡）
- 12:00 午餐：鸡胸肉沙拉（450大卡）
- 18:30 晚餐：糙米饭 + 西兰花（500大卡）
```

### 3. 图谱索引更新
```python
# 更新节点属性（合并现有属性）
updates = {
    "properties": {
        **(node.properties or {}),  # 保留现有属性
        "last_log_date": date,      # 更新最新日志日期
        "log_path": log_path,       # 更新日志路径
    }
}
await self.graph.update_node(node.id, updates)
```

**作用：**
- 图谱实体可以快速定位到相关日志文件
- 支持按日期查询日志（通过 `last_log_date`）

---

## 使用场景

### 场景1：记录饮食日志
```python
await log_writer.write_log(
    category="log_diet",
    message="晚餐：鸡胸肉200g + 西兰花（400大卡）",
    target_entity="减肥计划",
    tenant_id="tenant_001",
    user_id="user_001",
)
```

### 场景2：记录运动日志
```python
await log_writer.write_log(
    category="log_exercise",
    message="跑步5公里，用时30分钟",
    target_entity="健身计划",
    tenant_id="tenant_001",
    user_id="user_001",
)
```

### 场景3：记录面试日志
```python
await log_writer.write_log(
    category="log_interview",
    message="字节跳动一面：算法题通过，系统设计待改进",
    target_entity="求职计划",
    tenant_id="tenant_001",
    user_id="user_001",
)
```

---

## 注意事项

1. **类别验证：** 未知类别会自动降级为 `log_general`
2. **时区一致性：** 所有日志文件使用北京时间（UTC+8）
3. **文件追加：** 同一天的日志追加到同一个文件
4. **图谱更新：** 只更新第一个匹配的实体节点
5. **错误处理：** 图谱更新失败不影响日志写入（日志优先）

---

## 依赖关系

- **依赖：** `GraphStore`（图谱存储）
- **被依赖：** API 层、Consolidator（巩固器）
