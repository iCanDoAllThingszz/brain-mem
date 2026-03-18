# server/models/__init__.py 文档

## 文件整体功能说明

`server/models/__init__.py` 是 `server.models` 包的初始化文件，当前为空文件。

---

## 作用

作为Python包的标识文件，使 `server/models` 目录成为一个可导入的Python包。虽然文件内容为空，但它的存在允许其他模块通过以下方式导入：

```python
from server.models.node import Node
from server.models.relation import Relation
```

---

## 模块导出

当前文件为空，未显式导出任何内容。

---

## 包结构

`server/models` 包包含以下数据模型：

```
server/models/
├── __init__.py      # 包初始化文件（本文件）
├── node.py          # Node数据模型 - 记忆节点
└── relation.py      # Relation数据模型 - 节点关系
```

---

## 核心模型概览

### 1. node.py - Node数据模型

**功能：** 定义知识图谱中的记忆节点

**核心特性：**
- 支持4种记忆区域（semantic/episodic/procedural/emotional）
- 记忆衰减机制（decay_factor, retrieval_strength）
- 访问追踪（access_count, last_accessed）
- 情感标签（emotional_tag）
- 时间有效性（valid_from, valid_until）
- 多租户隔离（tenant_id, user_id）

**主要方法：**
- `to_neo4j_props()` - 转换为Neo4j属性字典
- `from_neo4j_props()` - 从Neo4j属性重建对象
- `validate_zone()` - 验证记忆区域
- `validate_status()` - 验证节点状态
- `validate_emotional_tag()` - 验证情感标签

**使用场景：**
```python
from server.models.node import Node

# 创建语义记忆节点
node = Node(
    name="Python编程语言",
    zone="semantic",
    summary="一种高级编程语言",
    importance=8.0
)

# 转换为Neo4j格式
props = node.to_neo4j_props(tenant_id="t1", user_id="u1")
```

---

### 2. relation.py - Relation数据模型

**功能：** 定义节点之间的有向关系

**核心特性：**
- 有向关系（from_id → to_id）
- 关系类型（type: RELATED_TO, CAUSES, PART_OF等）
- 置信度评分（confidence: 0-1）
- 时间有效性（valid_from, valid_until）
- 会话追踪（source_session）
- 自由扩展属性（properties）

**主要方法：**
- `to_neo4j_props()` - 转换为Neo4j属性字典
- `from_neo4j_record()` - 从Neo4j关系数据重建对象

**使用场景：**
```python
from server.models.relation import Relation

# 创建因果关系
relation = Relation(
    from_id="node_001",
    to_id="node_002",
    type="CAUSES",
    description="学习导致能力提升",
    confidence=0.9
)

# 转换为Neo4j格式
props = relation.to_neo4j_props()
```

---

## 调用关系图

```
server/models/
│
├── Node
│   ├── 被调用方
│   │   ├── server/engine/encoder.py → Node() 创建节点
│   │   ├── server/engine/retriever.py → Node.from_neo4j_props() 重建节点
│   │   ├── server/engine/consolidator.py → Node.to_neo4j_props() 更新节点
│   │   └── server/app.py → Node() 处理API请求
│   │
│   └── 调用方
│       ├── pydantic.BaseModel（继承）
│       ├── uuid.uuid4()（生成ID）
│       ├── datetime.utcnow()（时间戳）
│       └── json.dumps/loads（序列化）
│
└── Relation
    ├── 被调用方
    │   ├── server/engine/encoder.py → Relation() 创建关系
    │   ├── server/engine/retriever.py → Relation.from_neo4j_record() 重建关系
    │   └── server/app.py → Relation() 处理API请求
    │
    └── 调用方
        ├── pydantic.BaseModel（继承）
        ├── datetime.fromisoformat()（时间解析）
        └── json.dumps/loads（序列化）
```

---

## 数据流示例

### 创建记忆节点流程
```
1. 用户输入文本
   ↓
2. server/engine/encoder.py 分析输入
   ↓
3. 创建 Node 对象
   ↓
4. Node.to_neo4j_props() 转换为Neo4j格式
   ↓
5. 存储到Neo4j数据库
   ↓
6. 返回节点ID
```

### 检索记忆节点流程
```
1. 用户查询请求
   ↓
2. server/engine/retriever.py 执行Cypher查询
   ↓
3. Neo4j返回属性字典
   ↓
4. Node.from_neo4j_props() 重建对象
   ↓
5. 返回 Node 列表
```

### 创建关系流程
```
1. 识别两个相关节点
   ↓
2. 创建 Relation 对象
   ↓
3. Relation.to_neo4j_props() 转换为Neo4j格式
   ↓
4. 执行 CREATE (a)-[r:TYPE]->(b) Cypher
   ↓
5. 返回关系创建结果
```

---

## 潜在用途（未来扩展）

虽然当前为空，但 `__init__.py` 可以用于：

### 1. 统一导出接口
```python
"""
Brain Memory Models Package
Data models for memory nodes and relationships.
"""

from server.models.node import Node
from server.models.relation import Relation

__all__ = ["Node", "Relation"]
```

这样外部可以直接：
```python
from server.models import Node, Relation
```

### 2. 模型注册表
```python
# 模型注册表，用于动态查找
MODEL_REGISTRY = {
    "node": Node,
    "relation": Relation,
}

def get_model(model_name: str):
    """根据名称获取模型类"""
    return MODEL_REGISTRY.get(model_name)
```

### 3. 模型验证器
```python
from typing import Union

def validate_model(data: dict, model_type: str) -> Union[Node, Relation]:
    """统一的模型验证入口"""
    if model_type == "node":
        return Node(**data)
    elif model_type == "relation":
        return Relation(**data)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
```

### 4. 模型工具函数
```python
def serialize_model(model: Union[Node, Relation]) -> dict:
    """统一的序列化方法"""
    return model.model_dump()

def deserialize_model(data: dict, model_type: str) -> Union[Node, Relation]:
    """统一的反序列化方法"""
    if model_type == "node":
        return Node(**data)
    elif model_type == "relation":
        return Relation(**data)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
```

---

## 注意事项

1. **Pydantic依赖**: 两个模型都继承自 `pydantic.BaseModel`，提供自动验证
2. **Neo4j兼容性**: 模型设计考虑了Neo4j的数据类型限制
3. **多租户隔离**: Node模型支持 `tenant_id` 和 `user_id` 隔离
4. **时间处理**: 统一使用UTC时间，存储为ISO格式字符串
5. **JSON序列化**: 复杂对象（dict, list）需序列化为JSON字符串

---

## 建议

考虑在此文件中添加统一导出和工具函数：

```python
"""
Brain Memory Models Package
Data models for memory nodes and relationships in the knowledge graph.
"""

from server.models.node import Node
from server.models.relation import Relation

__version__ = "1.0.0"
__all__ = ["Node", "Relation"]

# 模型注册表
MODEL_REGISTRY = {
    "node": Node,
    "relation": Relation,
}

def get_model(model_name: str):
    """
    根据名称获取模型类
    
    Args:
        model_name: 模型名称（"node" 或 "relation"）
    
    Returns:
        对应的模型类
    
    Raises:
        ValueError: 未知的模型名称
    """
    if model_name not in MODEL_REGISTRY:
        raise ValueError(f"Unknown model: {model_name}. Available: {list(MODEL_REGISTRY.keys())}")
    return MODEL_REGISTRY[model_name]

def validate_and_create(model_name: str, data: dict):
    """
    验证数据并创建模型实例
    
    Args:
        model_name: 模型名称
        data: 模型数据字典
    
    Returns:
        模型实例（Node 或 Relation）
    """
    model_class = get_model(model_name)
    return model_class(**data)
```

这样可以简化导入和动态创建：
```python
# 简化前
from server.models.node import Node
from server.models.relation import Relation
node = Node(**data)

# 简化后
from server.models import Node, Relation, validate_and_create
node = validate_and_create("node", data)
```

---

## 模型对比

| 特性 | Node | Relation |
|------|------|----------|
| **主键** | id (uuid) | from_id + to_id + type |
| **时间字段** | created_at, updated_at, last_accessed, valid_from, valid_until | valid_from, valid_until |
| **置信度** | confidence (0-1) | confidence (0-1) |
| **扩展属性** | properties (dict) | properties (dict) |
| **特有字段** | zone, importance, emotional_tag, decay_factor, access_count | type, description, source_session |
| **Neo4j存储** | 节点属性 | 关系属性 |
| **隔离字段** | tenant_id, user_id | 无（继承自节点） |

---

## 相关文件

- `server/__init__.py` - server包初始化文件
- `server/engine/__init__.py` - engine子包初始化文件
- `server/app.py` - FastAPI应用主入口，使用这些模型处理API请求

---

## 使用示例

### 完整的节点-关系创建流程
```python
from server.models import Node, Relation

# 1. 创建两个节点
node1 = Node(
    name="Python",
    zone="semantic",
    summary="编程语言",
    importance=8.0,
    tags=["编程", "技术"]
)

node2 = Node(
    name="Web开发",
    zone="procedural",
    summary="网站开发技能",
    importance=7.0,
    tags=["技能", "开发"]
)

# 2. 创建关系
relation = Relation(
    from_id=node1.id,
    to_id=node2.id,
    type="USED_IN",
    description="Python用于Web开发",
    confidence=0.95
)

# 3. 转换为Neo4j格式
node1_props = node1.to_neo4j_props(tenant_id="t1", user_id="u1")
node2_props = node2.to_neo4j_props(tenant_id="t1", user_id="u1")
relation_props = relation.to_neo4j_props()

# 4. 存储到Neo4j（伪代码）
# CREATE (n1:Node $node1_props)
# CREATE (n2:Node $node2_props)
# CREATE (n1)-[r:USED_IN $relation_props]->(n2)
```
