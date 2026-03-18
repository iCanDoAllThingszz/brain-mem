# graph.py - Neo4j 图存储层

## 文件整体功能

`graph.py` 实现了基于 Neo4j 的异步图存储层，提供记忆节点（MemoryNode）和关系（Relation）的 CRUD 操作、图遍历、向量检索等功能。

**核心职责：**
- 异步连接和管理 Neo4j 数据库
- 节点的创建、更新、查询（按名称、别名、标签、模糊搜索）
- 关系的创建、更新、查询
- 图遍历（多跳关系）
- 记忆衰减（decay）和访问强化（retrieval practice）
- 节点合并（merge）
- 休眠节点（dormant）的查找和复活（revive）
- 向量嵌入索引和相似度检索

---

## 类：GraphStore

### 作用
异步 Neo4j 图存储，管理记忆节点和关系，支持多租户数据隔离。

### 初始化

```python
def __init__(self, uri: str, user: str, password: str) -> None
```

**参数：**
- `uri` (str): Neo4j bolt URI，例如 `bolt://localhost:7687`
- `user` (str): Neo4j 用户名
- `password` (str): Neo4j 密码

**功能：**
保存连接参数，但不立即连接（需要调用 `connect()`）。

**调用链路：**
- 被：服务启动时实例化
- 调用：无

---

### connect() - 建立连接

```python
async def connect(self) -> None
```

**功能：**
建立到 Neo4j 的异步连接并验证连通性。

**异常：**
- `neo4j_exc.ServiceUnavailable`: 连接失败

**调用链路：**
- 被：服务启动时调用
- 调用：`AsyncGraphDatabase.driver()`, `verify_connectivity()`

---

### close() - 关闭连接

```python
async def close(self) -> None
```

**功能：**
关闭 Neo4j 驱动连接。

**调用链路：**
- 被：服务关闭时调用
- 调用：`driver.close()`

---

## 节点操作

### 1. create_node() - 创建节点

```python
async def create_node(self, node: Node, tenant_id: str, user_id: str) -> Node
```

**功能：**
在图中创建一个新的记忆节点。

**参数：**
- `node` (Node): 节点实例
- `tenant_id` (str): 租户标识
- `user_id` (str): 用户标识

**返回值：**
- 创建后的 Node 对象（包含服务器分配的时间戳）

**关键逻辑：**
1. 调用 `node.to_neo4j_props()` 序列化节点属性
2. 使用 Cypher `CREATE (n:MemoryNode $props)` 创建节点
3. 返回创建后的节点

**调用链路：**
- 被：整合任务（consolidation）调用
- 调用：`node.to_neo4j_props()`, `session.run()`

**代码示例：**
```python
from server.models.node import Node

node = Node(
    id="node123",
    name="减肥计划",
    type="项目",
    zone="semantic",
    importance=0.8,
)
created = await graph.create_node(node, "tenant1", "user1")
```

---

### 2. update_node() - 更新节点

```python
async def update_node(self, node_id: str, updates: Dict[str, Any]) -> Node
```

**功能：**
更新现有节点的属性（部分更新）。

**参数：**
- `node_id` (str): 目标节点 ID
- `updates` (Dict): 要更新的属性字典

**返回值：**
- 更新后的 Node 对象

**异常：**
- `ValueError`: 节点不存在

**关键逻辑：**
1. 序列化复杂字段（emotional_tag, properties）为 JSON
2. 序列化日期时间字段为 ISO 字符串
3. 自动更新 `updated_at` 为当前时间
4. 使用 Cypher `SET n += $updates` 合并更新

**调用链路：**
- 被：节点属性修改时调用
- 调用：`session.run()`, `Node.from_neo4j_props()`

---

### 3. get_node() - 获取节点

```python
async def get_node(self, node_id: str) -> Optional[Node]
```

**功能：**
根据 ID 查询节点。

**参数：**
- `node_id` (str): 节点 ID

**返回值：**
- Node 对象，如果不存在则返回 None

**调用链路：**
- 被：节点查询时调用
- 调用：`session.run()`, `Node.from_neo4j_props()`

---

### 4. find_nodes_by_name() - 按名称查找

```python
async def find_nodes_by_name(self, name: str, tenant_id: str, user_id: str) -> List[Node]
```

**功能：**
精确匹配节点名称。

**参数：**
- `name` (str): 节点名称
- `tenant_id` (str): 租户标识
- `user_id` (str): 用户标识

**返回值：**
- 匹配的节点列表

**调用链路：**
- 被：实体识别后查找已存在节点
- 调用：`session.run()`, `Node.from_neo4j_props()`

---

### 5. find_nodes_by_alias() - 按别名查找

```python
async def find_nodes_by_alias(self, alias: str, tenant_id: str, user_id: str) -> List[Node]
```

**功能：**
查找别名列表中包含指定字符串的节点。

**参数：**
- `alias` (str): 别名字符串
- `tenant_id` (str): 租户标识
- `user_id` (str): 用户标识

**返回值：**
- 匹配的节点列表

**Cypher 查询：**
```cypher
MATCH (n:MemoryNode {tenant_id: $tenant_id, user_id: $user_id})
WHERE $alias IN n.aliases
RETURN n
```

**调用链路：**
- 被：实体消歧时调用
- 调用：`session.run()`, `Node.from_neo4j_props()`

---

### 6. find_nodes_by_tags() - 按标签查找

```python
async def find_nodes_by_tags(self, tags: List[str], tenant_id: str, user_id: str) -> List[Node]
```

**功能：**
查找包含所有指定标签的节点（AND 逻辑）。

**参数：**
- `tags` (List[str]): 标签列表
- `tenant_id` (str): 租户标识
- `user_id` (str): 用户标识

**返回值：**
- 匹配的节点列表

**Cypher 查询：**
```cypher
MATCH (n:MemoryNode {tenant_id: $tenant_id, user_id: $user_id})
WHERE ALL(tag IN $tags WHERE tag IN n.tags)
RETURN n
```

**调用链路：**
- 被：标签过滤查询时调用
- 调用：`session.run()`, `Node.from_neo4j_props()`

---

### 7. find_nodes_fuzzy() - 模糊搜索

```python
async def find_nodes_fuzzy(self, keyword: str, tenant_id: str, user_id: str) -> List[Node]
```

**功能：**
按关键词模糊搜索节点名称（CONTAINS 匹配，不区分大小写）。

**参数：**
- `keyword` (str): 搜索关键词
- `tenant_id` (str): 租户标识
- `user_id` (str): 用户标识

**返回值：**
- 匹配的节点列表

**Cypher 查询：**
```cypher
MATCH (n:MemoryNode {tenant_id: $tenant_id, user_id: $user_id})
WHERE toLower(n.name) CONTAINS toLower($keyword)
RETURN n
```

**调用链路：**
- 被：用户搜索时调用
- 调用：`session.run()`, `Node.from_neo4j_props()`

---

### 8. traverse_relations() - 遍历关系

```python
async def traverse_relations(self, node_id: str, max_depth: int = 2) -> List[Dict[str, Any]]
```

**功能：**
从指定节点出发，遍历所有出边关系，最多 max_depth 跳。

**参数：**
- `node_id` (str): 起始节点 ID
- `max_depth` (int): 最大遍历深度（默认 2）

**返回值：**
- 字典列表，每个字典包含：
  - `from_id`: 起始节点 ID
  - `to_id`: 目标节点 ID
  - `rel_type`: 关系类型
  - `rel_props`: 关系属性
  - `node_props`: 目标节点属性

**Cypher 查询：**
```cypher
MATCH path = (start:MemoryNode {id: $node_id})-[r*1..{max_depth}]->(end:MemoryNode)
UNWIND relationships(path) AS rel
RETURN startNode(rel).id AS from_id,
       endNode(rel).id AS to_id,
       type(rel) AS rel_type,
       properties(rel) AS rel_props,
       properties(endNode(rel)) AS node_props
```

**调用链路：**
- 被：上下文扩展时调用
- 调用：`session.run()`

---

## 关系操作

### 9. create_relation() - 创建关系

```python
async def create_relation(self, relation: Relation) -> Relation
```

**功能：**
在两个已存在节点之间创建有向关系。

**参数：**
- `relation` (Relation): 关系实例

**返回值：**
- 创建后的 Relation 对象

**异常：**
- `ValueError`: 任一节点不存在

**关键逻辑：**
1. 将关系类型转换为 Cypher 格式（大写，空格替换为下划线）
2. 使用 `MATCH` 确保两个节点存在
3. 使用 `CREATE` 创建关系

**Cypher 查询：**
```cypher
MATCH (a:MemoryNode {id: $from_id})
MATCH (b:MemoryNode {id: $to_id})
CREATE (a)-[r:REL_TYPE $props]->(b)
RETURN r, a.id AS from_id, b.id AS to_id, type(r) AS rel_type
```

**调用链路：**
- 被：整合任务创建关系时调用
- 调用：`relation.to_neo4j_props()`, `session.run()`, `Relation.from_neo4j_record()`

---

### 10. update_relation() - 更新关系

```python
async def update_relation(
    self, from_id: str, to_id: str, rel_type: str, updates: Dict[str, Any]
) -> None
```

**功能：**
更新现有关系的属性。

**参数：**
- `from_id` (str): 起始节点 ID
- `to_id` (str): 目标节点 ID
- `rel_type` (str): 关系类型
- `updates` (Dict): 要更新的属性

**调用链路：**
- 被：关系属性修改时调用
- 调用：`session.run()`

---

### 11. get_relations() - 获取节点关系

```python
async def get_relations(self, node_id: str) -> List[Relation]
```

**功能：**
获取节点的所有关系（入边和出边）。

**参数：**
- `node_id` (str): 节点 ID

**返回值：**
- Relation 对象列表

**Cypher 查询：**
```cypher
MATCH (n:MemoryNode {id: $node_id})-[r]-(m:MemoryNode)
RETURN startNode(r).id AS from_id, endNode(r).id AS to_id,
       type(r) AS rel_type, properties(r) AS rel_props
```

**调用链路：**
- 被：关系查询时调用
- 调用：`session.run()`, `Relation.from_neo4j_record()`

---

## 高级查询

### 12. find_active_nodes() - 查找活跃节点

```python
async def find_active_nodes(
    self,
    tenant_id: str,
    user_id: str,
    zone: Optional[str] = None,
    min_strength: float = 0.0,
) -> List[Node]
```

**功能：**
查找所有活跃节点，可选按记忆区（zone）和检索强度（retrieval_strength）过滤。

**参数：**
- `tenant_id` (str): 租户标识
- `user_id` (str): 用户标识
- `zone` (Optional[str]): 记忆区过滤（episodic/semantic/procedural/emotional）
- `min_strength` (float): 最小检索强度阈值

**返回值：**
- 活跃节点列表，按检索强度降序

**调用链路：**
- 被：上下文召回时调用
- 调用：`session.run()`, `Node.from_neo4j_props()`

---

### 13. update_access() - 更新访问记录

```python
async def update_access(self, node_id: str) -> None
```

**功能：**
记录节点访问，实现检索练习效应（retrieval practice effect）。

**关键逻辑：**
1. 访问计数 +1
2. 更新 `last_accessed` 为当前时间
3. 检索强度 +0.5（上限 10.0）

**Cypher 查询：**
```cypher
MATCH (n:MemoryNode {id: $node_id})
SET n.access_count = n.access_count + 1,
    n.last_accessed = $now,
    n.retrieval_strength = CASE
        WHEN n.retrieval_strength + 0.5 > 10.0 THEN 10.0
        ELSE n.retrieval_strength + 0.5
    END
```

**调用链路：**
- 被：节点被召回时调用
- 调用：`session.run()`

**重要性：**
实现了记忆强化机制——每次召回都会增强记忆，模拟人类记忆的检索练习效应。

---

### 14. apply_decay() - 应用记忆衰减

```python
async def apply_decay(
    self, tenant_id: str, user_id: str, base_half_life_days: int = 30
) -> None
```

**功能：**
应用记忆衰减算法，模拟遗忘曲线。

**参数：**
- `tenant_id` (str): 租户标识
- `user_id` (str): 用户标识
- `base_half_life_days` (int): 基础半衰期（天数，默认 30）

**衰减公式：**
```
effective_half_life = base_half_life × (1 + importance/10) × zone_factor
new_strength = old_strength × decay_factor × exp(-0.693147 / effective_half_life × days_elapsed)
```

**记忆区系数（zone_factor）：**
- episodic（情景记忆）: 0.5（衰减快）
- semantic（语义记忆）: 2.0（衰减慢）
- procedural（程序记忆）: 3.0（衰减最慢）
- emotional（情感记忆）: 1.0（中等）

**休眠转换：**
- 当 `retrieval_strength < 0.1` 时，节点状态转为 `dormant`（休眠）

**调用链路：**
- 被：定时任务（每日/每周）调用
- 调用：`session.run()`

**重要性：**
实现了记忆的自然遗忘，重要性高的记忆衰减慢，不同类型记忆有不同的遗忘速度。

---

### 15. merge_nodes() - 合并节点

```python
async def merge_nodes(self, keep_id: str, remove_id: str) -> None
```

**功能：**
合并两个节点：将 remove 节点的关系转移到 keep 节点，合并别名和标签，然后删除 remove 节点。

**参数：**
- `keep_id` (str): 保留节点 ID
- `remove_id` (str): 删除节点 ID

**异常：**
- `ValueError`: 任一节点不存在

**关键逻辑：**
1. 验证两个节点都存在
2. 转移出边关系（remove → target 变为 keep → target）
3. 转移入边关系（source → remove 变为 source → keep）
4. 合并 aliases、tags、source_sessions（去重）
5. 删除 remove 节点及其剩余关系

**调用链路：**
- 被：实体消歧时调用
- 调用：`session.run()`

**注意事项：**
- 不依赖 APOC 插件，使用原生 Cypher
- 关系类型统一转换为 `RELATED_TO`
- 合并操作不可逆

---

### 16. find_dormant_nodes() - 查找休眠节点

```python
async def find_dormant_nodes(
    self, keywords: List[str], tenant_id: str, user_id: str, limit: int = 5
) -> List[Node]
```

**功能：**
按关键词搜索休眠节点（status='dormant'）。

**参数：**
- `keywords` (List[str]): 关键词列表
- `tenant_id` (str): 租户标识
- `user_id` (str): 用户标识
- `limit` (int): 返回数量上限（默认 5）

**返回值：**
- 休眠节点列表，按重要性降序

**Cypher 查询：**
```cypher
MATCH (n:MemoryNode {tenant_id: $tenant_id, user_id: $user_id, status: 'dormant'})
WHERE any(kw IN $keywords WHERE n.name CONTAINS kw OR any(a IN n.aliases WHERE a CONTAINS kw))
RETURN n ORDER BY n.importance DESC LIMIT $limit
```

**调用链路：**
- 被：上下文召回时调用（当活跃节点不足时）
- 调用：`session.run()`

---

### 17. revive_if_dormant() - 复活休眠节点

```python
async def revive_if_dormant(self, node_id: str) -> bool
```

**功能：**
将休眠节点复活为活跃状态，重置检索强度为 5.0。

**参数：**
- `node_id` (str): 节点 ID

**返回值：**
- True: 成功复活
- False: 节点不是休眠状态或不存在

**Cypher 查询：**
```cypher
MATCH (n:MemoryNode {id: $node_id, status: 'dormant'})
SET n.status = 'active', n.retrieval_strength = 5.0, n.last_accessed = $now
RETURN n.id AS revived
```

**调用链路：**
- 被：休眠节点被召回时调用
- 调用：`session.run()`

---

### 18. add_aliases() - 添加别名

```python
async def add_aliases(self, node_id: str, aliases: List[str]) -> None
```

**功能：**
为节点添加别名（去重合并）。

**参数：**
- `node_id` (str): 节点 ID
- `aliases` (List[str]): 别名列表

**Cypher 查询：**
```cypher
MATCH (n:MemoryNode {id: $node_id})
SET n.aliases = n.aliases + [x IN $aliases WHERE NOT x IN n.aliases]
```

**调用链路：**
- 被：实体识别时调用
- 调用：`session.run()`

---

### 19. merge_tags() - 合并标签

```python
async def merge_tags(self, node_id: str, new_tags: List[str]) -> None
```

**功能：**
为节点合并新标签（去重）。

**参数：**
- `node_id` (str): 节点 ID
- `new_tags` (List[str]): 新标签列表

**Cypher 查询：**
```cypher
MATCH (n:MemoryNode {id: $node_id})
SET n.tags = n.tags + [x IN $new_tags WHERE NOT x IN n.tags]
```

**调用链路：**
- 被：标签更新时调用
- 调用：`session.run()`

---

## 向量检索

### 20. ensure_vector_index() - 确保向量索引

```python
async def ensure_vector_index(self)
```

**功能：**
创建向量索引（如果不存在）。

**索引配置：**
- 索引名称：`memory_embedding`
- 向量维度：1536
- 相似度函数：cosine

**Cypher 查询：**
```cypher
CREATE VECTOR INDEX memory_embedding IF NOT EXISTS
FOR (n:MemoryNode) ON (n.embedding)
OPTIONS {indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
}}
```

**调用链路：**
- 被：服务启动时调用
- 调用：`session.run()`

---

### 21. update_node_embedding() - 更新节点嵌入

```python
async def update_node_embedding(self, node_id: str, embedding: list)
```

**功能：**
更新节点的嵌入向量。

**参数：**
- `node_id` (str): 节点 ID
- `embedding` (list): 1536 维向量列表

**调用链路：**
- 被：嵌入生成任务调用
- 调用：`session.run()`

---

### 22. vector_search() - 向量相似度搜索

```python
async def vector_search(self, query_embedding: list, top_k: int = 10, min_score: float = 0.5) -> list
```

**功能：**
基于向量相似度搜索节点。

**参数：**
- `query_embedding` (list): 查询向量（1536 维）
- `top_k` (int): 返回数量上限（默认 10）
- `min_score` (float): 最小相似度阈值（默认 0.5）

**返回值：**
- 字典列表，每个字典包含：
  - `node`: 节点属性字典
  - `score`: 相似度分数

**Cypher 查询：**
```cypher
CALL db.index.vector.queryNodes('memory_embedding', $top_k, $embedding)
YIELD node, score
WHERE score >= $min_score AND node.status <> 'suppressed'
RETURN node, score
ORDER BY score DESC
```

**调用链路：**
- 被：语义检索时调用
- 调用：`session.run()`

---

### 23. find_nodes_without_embedding() - 查找无嵌入节点

```python
async def find_nodes_without_embedding(self, tenant_id: str, user_id: str) -> list
```

**功能：**
查找所有活跃但没有嵌入向量的节点。

**参数：**
- `tenant_id` (str): 租户标识
- `user_id` (str): 用户标识

**返回值：**
- 字典列表，每个字典包含：id, name, summary

**调用链路：**
- 被：嵌入生成任务调用
- 调用：`session.run()`

---

## 调用链路总览

```
服务启动
  → GraphStore.__init__()
  → connect()
    → AsyncGraphDatabase.driver()
    → verify_connectivity()
  → ensure_vector_index()

整合任务
  → create_node()
    → node.to_neo4j_props()
    → session.run()
  → create_relation()
    → relation.to_neo4j_props()
    → session.run()

上下文召回
  → find_active_nodes()
    → session.run()
  → vector_search()
    → session.run()
  → find_dormant_nodes()
    → session.run()
  → update_access()
    → session.run()
  → revive_if_dormant()
    → session.run()

定时任务
  → apply_decay()
    → session.run()

实体消歧
  → find_nodes_by_name() / find_nodes_by_alias()
    → session.run()
  → merge_nodes()
    → session.run()

服务关闭
  → close()
    → driver.close()
```

---

## 重要注意事项

1. **异步操作**：所有方法都是异步的，必须使用 `await` 调用
2. **多租户隔离**：所有节点都携带 `tenant_id` 和 `user_id` 属性，确保数据隔离
3. **记忆衰减**：基于遗忘曲线，重要性和记忆区影响衰减速度
4. **检索练习**：每次访问节点都会增强记忆（+0.5 强度）
5. **休眠机制**：强度 < 0.1 的节点自动转为休眠，可通过关键词搜索复活
6. **节点合并**：不可逆操作，需谨慎使用
7. **向量检索**：需要 Neo4j 5.11+ 支持向量索引
8. **关系类型**：Cypher 中关系类型会转换为大写+下划线格式

---

## 性能优化建议

1. **索引覆盖**：确保 tenant_id, user_id, status, zone 等常用字段有索引
2. **批量操作**：使用事务包裹多个节点/关系创建
3. **向量索引**：定期更新嵌入向量，保持索引最新
4. **衰减频率**：根据数据量调整衰减任务频率（每日/每周）
5. **休眠清理**：定期清理长期休眠且重要性低的节点
