# node.py 文档

## 文件整体功能说明

`server/models/node.py` 定义了brain-memory服务中的核心数据模型 `Node`，用于表示存储在Neo4j知识图谱中的记忆节点。该模型支持多种记忆区域（语义、情景、程序性、情感），并具备记忆衰减、访问追踪、情感标签等高级功能。

---

## 类：Node

### 作用
`Node` 是知识图谱中的记忆节点模型，继承自 `pydantic.BaseModel`，提供数据验证、序列化和反序列化功能。

### 核心字段

| 字段名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `id` | str | uuid4() | 全局唯一标识符 |
| `name` | str | 必填 | 节点主名称 |
| `aliases` | List[str] | [] | 别名列表 |
| `tags` | List[str] | [] | 多维度标签（非互斥） |
| `summary` | str | "" | 一句话摘要 |
| `content` | str | "" | 详细内容（长文本） |
| `zone` | str | 必填 | 记忆区域：semantic/episodic/procedural/emotional |
| `importance` | float | 5.0 | 重要性权重（0-10） |
| `emotional_tag` | Dict | {"type": "neutral", "intensity": 0} | 情感标签 |
| `confidence` | float | 1.0 | 置信度（0-1） |
| `created_at` | datetime | utcnow() | 创建时间 |
| `updated_at` | datetime | utcnow() | 更新时间 |
| `last_accessed` | datetime | utcnow() | 最后访问时间 |
| `valid_from` | Optional[datetime] | None | 有效期开始时间 |
| `valid_until` | Optional[datetime] | None | 有效期结束时间 |
| `access_count` | int | 0 | 访问次数 |
| `decay_factor` | float | 1.0 | 记忆衰减因子 |
| `retrieval_strength` | float | 0.0 | 检索强度（默认等于importance） |
| `status` | str | "active" | 节点状态：active/dormant/suppressed |
| `version` | int | 1 | 版本号 |
| `source_sessions` | List[str] | [] | 来源会话ID列表 |
| `context_snapshot` | str | "" | 创建时的上下文快照 |
| `properties` | Dict[str, Any] | {} | 自由扩展属性 |

---

## 方法详解

### 1. `model_post_init(self, __context: Any) -> None`

**功能：** Pydantic模型初始化后的钩子函数，自动设置 `retrieval_strength`。

**参数：**
- `__context`: Pydantic内部上下文（未使用）

**返回值：** None

**逻辑：**
```python
if self.retrieval_strength == 0.0 and self.importance > 0:
    self.retrieval_strength = self.importance
```
如果 `retrieval_strength` 未显式设置（为0），则自动设为 `importance` 的值。

**调用链路：**
- 被 Pydantic 自动调用（模型实例化后）

---

### 2. `validate_zone(cls, v: str) -> str`

**功能：** 验证 `zone` 字段的合法性。

**参数：**
- `v`: 待验证的zone值

**返回值：** 验证通过的zone值

**逻辑：**
```python
valid_zones = {"semantic", "episodic", "procedural", "emotional"}
if v not in valid_zones:
    raise ValueError(f"zone must be one of {valid_zones}, got '{v}'")
```

**调用链路：**
- 被 Pydantic 自动调用（字段验证时）

**注意事项：**
- 仅允许4种记忆区域：语义、情景、程序性、情感
- 不合法的值会抛出 `ValueError`

---

### 3. `validate_status(cls, v: str) -> str`

**功能：** 验证 `status` 字段的合法性。

**参数：**
- `v`: 待验证的status值

**返回值：** 验证通过的status值

**逻辑：**
```python
valid_statuses = {"active", "dormant", "suppressed"}
if v not in valid_statuses:
    raise ValueError(f"status must be one of {valid_statuses}, got '{v}'")
```

**调用链路：**
- 被 Pydantic 自动调用（字段验证时）

---

### 4. `validate_emotional_tag(cls, v: Dict[str, Any]) -> Dict[str, Any]`

**功能：** 验证并规范化 `emotional_tag` 字段。

**参数：**
- `v`: 待验证的情感标签字典

**返回值：** 规范化后的情感标签

**逻辑：**
```python
valid_types = {"joy", "sadness", "anger", "fear", "surprise", "neutral"}
# 自动补全缺失字段
if "type" not in v:
    v["type"] = "neutral"
if "intensity" not in v:
    v["intensity"] = 0
# 验证type和intensity范围
```

**调用链路：**
- 被 Pydantic 自动调用（字段验证时）

**注意事项：**
- 自动补全缺失的 `type` 和 `intensity`
- `intensity` 必须在 0-10 范围内

---

### 5. `to_neo4j_props(self, tenant_id: str, user_id: str) -> Dict[str, Any]`

**功能：** 将Node对象转换为Neo4j兼容的属性字典。

**参数：**
- `tenant_id`: 租户ID（用于数据隔离）
- `user_id`: 用户ID（用于数据隔离）

**返回值：** Neo4j属性字典

**关键逻辑：**
```python
# 1. 转换datetime为ISO字符串
for field in ("created_at", "updated_at", "last_accessed", "valid_from", "valid_until"):
    if data[field] is not None:
        data[field] = data[field].isoformat()

# 2. 序列化复杂字段为JSON字符串
data["emotional_tag"] = json.dumps(data["emotional_tag"])
data["properties"] = json.dumps(data["properties"])

# 3. 添加隔离字段
data["tenant_id"] = tenant_id
data["user_id"] = user_id
```

**调用链路：**
- 被 `server/engine/__init__.py` 中的 `create_node()` 调用
- 被 `update_node()` 调用

**注意事项：**
- Neo4j原生支持列表类型（aliases, tags, source_sessions）
- 复杂对象（emotional_tag, properties）需序列化为JSON字符串
- 必须添加 `tenant_id` 和 `user_id` 实现多租户隔离

---

### 6. `from_neo4j_props(cls, props: Dict[str, Any]) -> "Node"`

**功能：** 从Neo4j属性字典重建Node对象。

**参数：**
- `props`: Neo4j查询返回的属性字典

**返回值：** Node实例

**关键逻辑：**
```python
# 1. 移除隔离字段（不属于Node模型）
data.pop("tenant_id", None)
data.pop("user_id", None)

# 2. 反序列化JSON字符串
for field in ("emotional_tag", "properties"):
    if isinstance(data.get(field), str):
        data[field] = json.loads(data[field])

# 3. 解析datetime字符串
for field in ("created_at", "updated_at", "last_accessed", "valid_from", "valid_until"):
    if data.get(field) and isinstance(data[field], str):
        data[field] = datetime.fromisoformat(data[field])
```

**调用链路：**
- 被 `server/engine/__init__.py` 中的 `get_node()` 调用
- 被 `list_nodes()` 调用
- 被 `search_nodes()` 调用

**注意事项：**
- 与 `to_neo4j_props()` 互为逆操作
- 必须正确处理JSON反序列化和datetime解析

---

## 调用关系图

```
Node类
├── 被调用方
│   ├── server/engine/__init__.py::create_node() → to_neo4j_props()
│   ├── server/engine/__init__.py::update_node() → to_neo4j_props()
│   ├── server/engine/__init__.py::get_node() → from_neo4j_props()
│   ├── server/engine/__init__.py::list_nodes() → from_neo4j_props()
│   └── server/engine/__init__.py::search_nodes() → from_neo4j_props()
│
└── 调用方
    ├── pydantic.BaseModel（继承）
    ├── uuid.uuid4()（生成ID）
    ├── datetime.utcnow()（时间戳）
    └── json.dumps/loads（序列化）
```

---

## 关键逻辑说明

### 1. 记忆区域（zone）设计
- **semantic（语义）**: 事实性知识（如"Python是编程语言"）
- **episodic（情景）**: 个人经历（如"2024年去了上海"）
- **procedural（程序性）**: 技能知识（如"如何骑自行车"）
- **emotional（情感）**: 情感记忆（如"失恋的痛苦"）

### 2. 记忆衰减机制
- `decay_factor`: 衰减因子，随时间降低记忆强度
- `retrieval_strength`: 检索强度，初始值等于 `importance`
- `access_count` 和 `last_accessed`: 追踪访问频率，用于计算衰减

### 3. 多租户隔离
- 通过 `tenant_id` 和 `user_id` 实现数据隔离
- 这两个字段仅存储在Neo4j中，不属于Node模型本身
- 查询时必须带上这两个字段过滤条件

### 4. 时间有效性
- `valid_from` 和 `valid_until`: 支持时间范围查询
- 可用于实现"临时记忆"或"过期知识"

### 5. 情感标签
- 支持6种情感类型：joy, sadness, anger, fear, surprise, neutral
- `intensity` 范围0-10，表示情感强度
- 可用于情感驱动的记忆检索

---

## 代码示例

### 创建节点
```python
from server.models.node import Node
from datetime import datetime

node = Node(
    name="Python编程语言",
    zone="semantic",
    summary="一种高级编程语言",
    content="Python是一种解释型、面向对象的编程语言...",
    tags=["编程", "技术", "开发"],
    importance=8.0,
    emotional_tag={"type": "joy", "intensity": 7}
)

# 转换为Neo4j属性
props = node.to_neo4j_props(tenant_id="tenant_001", user_id="user_123")
```

### 从Neo4j重建节点
```python
# 假设从Neo4j查询得到props
neo4j_props = {
    "id": "abc-123",
    "name": "Python编程语言",
    "zone": "semantic",
    "emotional_tag": '{"type": "joy", "intensity": 7}',
    "created_at": "2024-01-01T00:00:00",
    "tenant_id": "tenant_001",
    "user_id": "user_123",
    # ... 其他字段
}

node = Node.from_neo4j_props(neo4j_props)
print(node.name)  # "Python编程语言"
```

---

## 注意事项

1. **ID生成**: 使用UUID4保证全局唯一性
2. **时间处理**: 所有时间字段使用UTC时间
3. **验证器**: 使用Pydantic的 `@field_validator` 确保数据合法性
4. **序列化**: 复杂对象必须序列化为JSON字符串存储到Neo4j
5. **隔离字段**: `tenant_id` 和 `user_id` 仅用于Neo4j存储，不属于模型本身
