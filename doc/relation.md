# relation.py 文档

## 文件整体功能说明

`server/models/relation.py` 定义了brain-memory服务中的关系数据模型 `Relation`，用于表示Neo4j图谱中两个记忆节点之间的有向关系。该模型支持时间有效性、置信度评分和自由扩展属性。

---

## 类：Relation

### 作用
`Relation` 是知识图谱中的关系模型，继承自 `pydantic.BaseModel`，用于描述节点之间的语义连接（如"相关"、"导致"、"属于"等）。

### 核心字段

| 字段名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `from_id` | str | 必填 | 源节点ID |
| `to_id` | str | 必填 | 目标节点ID |
| `type` | str | 必填 | 关系类型（如RELATED_TO, CAUSES, PART_OF） |
| `description` | str | "" | 关系的自然语言描述 |
| `valid_from` | Optional[datetime] | None | 关系有效期开始时间 |
| `valid_until` | Optional[datetime] | None | 关系有效期结束时间 |
| `confidence` | float | 1.0 | 置信度（0-1） |
| `source_session` | str | "" | 创建该关系的会话ID |
| `properties` | Dict[str, Any] | {} | 自由扩展属性 |

---

## 方法详解

### 1. `to_neo4j_props(self) -> Dict[str, Any]`

**功能：** 将Relation对象转换为Neo4j兼容的属性字典。

**参数：** 无

**返回值：** Neo4j关系属性字典

**关键逻辑：**
```python
data = self.model_dump()
# 移除节点匹配字段（用于查询，不存储在边上）
data.pop("from_id")
data.pop("to_id")
data.pop("type")

# 转换datetime为ISO字符串
for field in ("valid_from", "valid_until"):
    if data[field] is not None and isinstance(data[field], datetime):
        data[field] = data[field].isoformat()

# 序列化复杂字段
data["properties"] = json.dumps(data["properties"])
```

**调用链路：**
- 被 `server/engine/__init__.py` 中的 `create_relation()` 调用

**注意事项：**
- `from_id`, `to_id`, `type` 不存储在关系属性中
- 这三个字段用于Cypher查询的节点匹配和关系类型指定
- Neo4j关系的类型在创建时指定，不作为属性存储

---

### 2. `from_neo4j_record(cls, from_id: str, to_id: str, rel_type: str, props: Dict[str, Any]) -> "Relation"`

**功能：** 从Neo4j关系数据重建Relation对象。

**参数：**
- `from_id`: 源节点ID
- `to_id`: 目标节点ID
- `rel_type`: 关系类型
- `props`: Neo4j查询返回的关系属性字典

**返回值：** Relation实例

**关键逻辑：**
```python
data = dict(props)
# 补充节点和类型信息
data["from_id"] = from_id
data["to_id"] = to_id
data["type"] = rel_type

# 反序列化JSON字符串
if isinstance(data.get("properties"), str):
    data["properties"] = json.loads(data["properties"])

# 解析datetime字符串
for field in ("valid_from", "valid_until"):
    if data.get(field) and isinstance(data[field], str):
        data[field] = datetime.fromisoformat(data[field])
```

**调用链路：**
- 被 `server/engine/__init__.py` 中的 `get_relations()` 调用
- 被 `list_relations()` 调用

**注意事项：**
- 与 `to_neo4j_props()` 互为逆操作
- 必须从Cypher查询结果中提取 `from_id`, `to_id`, `rel_type`

---

## 调用关系图

```
Relation类
├── 被调用方
│   ├── server/engine/__init__.py::create_relation() → to_neo4j_props()
│   ├── server/engine/__init__.py::get_relations() → from_neo4j_record()
│   └── server/engine/__init__.py::list_relations() → from_neo4j_record()
│
└── 调用方
    ├── pydantic.BaseModel（继承）
    ├── datetime.fromisoformat()（时间解析）
    └── json.dumps/loads（序列化）
```

---

## 关键逻辑说明

### 1. 关系类型设计
关系类型（`type`）是自由文本，常见类型包括：
- **RELATED_TO**: 一般关联
- **CAUSES**: 因果关系
- **PART_OF**: 部分-整体关系
- **SIMILAR_TO**: 相似关系
- **CONTRADICTS**: 矛盾关系
- **DERIVED_FROM**: 派生关系

### 2. 时间有效性
- `valid_from` 和 `valid_until`: 支持时间范围查询
- 可用于实现"临时关系"或"历史关系"
- 例如："A在2020年是B的员工"（valid_until=2021-01-01）

### 3. 置信度机制
- `confidence`: 表示关系的可信程度（0-1）
- 可用于模糊推理或不确定性传播
- 例如："A可能导致B"（confidence=0.7）

### 4. 会话追踪
- `source_session`: 记录创建该关系的会话ID
- 可用于追溯关系来源，支持会话级别的回滚

### 5. 扩展属性
- `properties`: 自由键值对，支持任意元数据
- 例如：`{"weight": 0.8, "context": "工作场景"}`

---

## 代码示例

### 创建关系
```python
from server.models.relation import Relation
from datetime import datetime

relation = Relation(
    from_id="node_001",
    to_id="node_002",
    type="CAUSES",
    description="学习Python导致编程能力提升",
    confidence=0.9,
    source_session="session_123",
    properties={"context": "技能学习", "weight": 0.85}
)

# 转换为Neo4j属性
props = relation.to_neo4j_props()
# props不包含from_id, to_id, type（这些用于Cypher查询）
```

### 从Neo4j重建关系
```python
# 假设从Neo4j查询得到关系数据
neo4j_props = {
    "description": "学习Python导致编程能力提升",
    "confidence": 0.9,
    "source_session": "session_123",
    "properties": '{"context": "技能学习", "weight": 0.85}',
    "valid_from": "2024-01-01T00:00:00",
    "valid_until": None
}

relation = Relation.from_neo4j_record(
    from_id="node_001",
    to_id="node_002",
    rel_type="CAUSES",
    props=neo4j_props
)

print(relation.type)  # "CAUSES"
print(relation.confidence)  # 0.9
```

### Neo4j Cypher查询示例
```cypher
// 创建关系（使用to_neo4j_props()的结果）
MATCH (a:Node {id: $from_id}), (b:Node {id: $to_id})
CREATE (a)-[r:CAUSES $props]->(b)

// 查询关系（用于from_neo4j_record()）
MATCH (a:Node {id: $from_id})-[r]->(b:Node {id: $to_id})
RETURN a.id AS from_id, b.id AS to_id, type(r) AS rel_type, properties(r) AS props
```

---

## 与Node的协作

### 关系创建流程
```
1. 用户请求创建关系
   ↓
2. server/engine/__init__.py::create_relation()
   ↓
3. 验证from_id和to_id对应的节点存在
   ↓
4. Relation.to_neo4j_props() 生成属性字典
   ↓
5. 执行Cypher: CREATE (a)-[r:TYPE $props]->(b)
   ↓
6. 返回创建结果
```

### 关系查询流程
```
1. 用户请求查询关系
   ↓
2. server/engine/__init__.py::get_relations()
   ↓
3. 执行Cypher: MATCH (a)-[r]->(b) WHERE ...
   ↓
4. 遍历查询结果
   ↓
5. Relation.from_neo4j_record() 重建对象
   ↓
6. 返回Relation列表
```

---

## 注意事项

1. **关系方向**: 所有关系都是有向的（from_id → to_id）
2. **类型命名**: 建议使用大写下划线格式（如RELATED_TO）
3. **属性存储**: `from_id`, `to_id`, `type` 不存储在关系属性中
4. **时间处理**: 所有时间字段使用UTC时间
5. **序列化**: `properties` 必须序列化为JSON字符串存储到Neo4j
6. **置信度范围**: 必须在0-1之间，由Pydantic自动验证

---

## 常见关系类型参考

| 类型 | 说明 | 示例 |
|------|------|------|
| RELATED_TO | 一般关联 | "Python" → "编程语言" |
| CAUSES | 因果关系 | "学习" → "能力提升" |
| PART_OF | 部分-整体 | "函数" → "Python语法" |
| SIMILAR_TO | 相似关系 | "Java" → "C++" |
| CONTRADICTS | 矛盾关系 | "观点A" → "观点B" |
| DERIVED_FROM | 派生关系 | "结论" → "前提" |
| PRECEDES | 时间先后 | "事件A" → "事件B" |
| LOCATED_IN | 空间关系 | "上海" → "中国" |
| OWNED_BY | 所属关系 | "项目" → "团队" |
| DEPENDS_ON | 依赖关系 | "模块A" → "模块B" |
