# consolidator.py - 记忆巩固器

## 文件整体功能

`Consolidator` 是 brain-memory 服务的记忆巩固器，对应人脑的睡眠巩固机制。

**核心职责：**
- 将缓冲区（EncoderBuffer）中的记忆单元转移到长期图谱（Neo4j）
- 实体插入/更新/合并（根据encoder的action字段）
- 关系创建与失效（支持干扰检测）
- 模式发现与冲突解决
- 孤儿节点修复（建议缺失关系）
- 创造性重组（发现跨领域洞察）
- 图谱清洁（LLM驱动的节点合并/降级/休眠）
- 隐含关系推导（v3新增，推导人物关系）
- 间隔重复标记（标记需要复习的记忆）

**设计理念（v3）：**
- 模拟人脑的睡眠巩固过程（整理、归纳、遗忘）
- 多阶段处理：写入 → 模式发现 → 冲突解决 → 图谱清洁 → 关系推导
- 自适应学习：别名学习、关系推导、创造性重组

---

## 类：Consolidator

### 作用
记忆巩固器，将短期记忆（缓冲区）转移到长期记忆（图谱）。

### 初始化方法

```python
def __init__(self, graph: GraphStore, tag_dict: TagDict, buffer: EncoderBuffer) -> None
```

**参数：**
- `graph`: GraphStore 实例，用于图谱操作
- `tag_dict`: TagDict 实例，用于标签管理
- `buffer`: EncoderBuffer 实例，用于读取和归档记忆单元

---

## 核心方法

### 1. consolidate - 执行睡眠巩固

```python
async def consolidate(self, tenant_id: str, user_id: str) -> Dict[str, Any]
```

**功能：** 执行完整的睡眠巩固流程：缓冲区 → 长期图谱。

**参数：**
- `tenant_id`: 租户ID
- `user_id`: 用户ID

**返回值：**
```python
{
    "nodes_created": int,           # 创建的节点数
    "nodes_updated": int,           # 更新的节点数
    "nodes_merged": int,            # 合并的节点数
    "relations_created": int,       # 创建的关系数
    "patterns_discovered": List[str],  # 发现的模式
    "conflicts_found": List[str],   # 发现的冲突
    "conflicts_resolved": int,      # 解决的冲突数
    "units_processed": int,         # 处理的记忆单元数
    "units_skipped": int,           # 跳过的低重要性单元数
    "insights_created": int,        # 创造性重组生成的洞察数
    "llm_review_merged": int,       # LLM图谱审查合并的节点数
    "llm_review_demoted": int,      # LLM图谱审查降级的节点数
    "llm_review_dormant": int,      # LLM图谱审查休眠的节点数
    "inferred_relations": int,      # 推导的隐含关系数
    "orphans_handled": int,         # 处理的孤儿节点数
    "memories_marked_for_review": int,  # 标记为需要复习的记忆数
}
```

**执行流程（8个阶段）：**

**阶段1：读取缓冲区**
- 读取所有未归档的记忆单元
- 过滤低重要性单元（importance < 3.0）

**阶段2：实体与关系写入**
- 遍历每个记忆单元
- 插入/更新/合并实体（根据action字段）
- 创建关系
- 处理干扰（失效旧关系）
- 归档已处理的单元

**阶段3：模式发现**
- 使用LLM分析记忆片段
- 识别跨事件模式、反复出现的主题
- 检测冲突信息

**阶段4：冲突解决**
- 扫描带冲突标记的节点
- 使用LLM决定如何解决（keep_new/keep_old/keep_both/merge）

**阶段5：孤儿节点修复**
- 找出无关系的节点
- 使用LLM建议缺失关系

**阶段6：创造性重组**
- 随机组合不同记忆片段
- 尝试发现有价值的洞察

**阶段7：图谱清洁（LLM驱动）**
- 分批审查所有活跃节点
- LLM决定：keep/merge/demote/dormant
- 执行合并、降级、休眠操作

**阶段8：隐含关系推导（v3新增）**
- 扫描人物节点及其已有关系
- 使用LLM推导缺失的隐含关系（如同事关系）

**阶段9：孤儿节点处理**
- 提醒节点：连接到用户主节点
- 低重要性旧节点：标记为休眠

**阶段10：衰减与间隔重复**
- 应用记忆衰减（降低检索强度）
- 标记需要复习的重要记忆

**代码示例：**
```python
# 执行巩固
stats = await consolidator.consolidate(
    tenant_id="tenant_001",
    user_id="user_001",
)
# 结果：
# {
#     "nodes_created": 5,
#     "nodes_updated": 3,
#     "nodes_merged": 2,
#     "relations_created": 8,
#     "patterns_discovered": ["用户最近频繁提到跳槽"],
#     "conflicts_found": [],
#     "conflicts_resolved": 0,
#     "units_processed": 10,
#     "units_skipped": 2,
#     "insights_created": 1,
#     "llm_review_merged": 3,
#     "inferred_relations": 4,
#     "memories_marked_for_review": 2,
# }
```

**调用链路：**
- 被调用：定时任务（如每天凌晨执行）
- 调用：
  - `self.buffer.read_unarchived()` → 读取缓冲区
  - `self._upsert_entity()` → 插入/更新实体
  - `self._upsert_relation()` → 创建关系
  - `self._invalidate_relations()` → 失效旧关系
  - `self._discover_patterns()` → 模式发现
  - `self._resolve_conflicts()` → 冲突解决
  - `self._repair_orphans()` → 孤儿节点修复
  - `self._creative_recombination()` → 创造性重组
  - `self._llm_graph_review()` → 图谱清洁
  - `self._infer_implicit_relations()` → 隐含关系推导
  - `self._handle_orphan_nodes()` → 孤儿节点处理
  - `self.graph.apply_decay()` → 应用衰减
  - `self._check_spaced_repetition()` → 间隔重复检查

---

## 内部辅助方法

### 1. _upsert_entity - 插入/更新实体

```python
async def _upsert_entity(
    self, entity: Dict[str, Any], tenant_id: str, user_id: str, unit: Dict[str, Any],
) -> Tuple[Optional[str], bool, bool]
```

**功能：** 根据encoder v2的action字段插入或更新实体。

**参数：**
- `entity`: 实体字典（包含name、action、summary等）
- `tenant_id`: 租户ID
- `user_id`: 用户ID
- `unit`: 记忆单元（包含importance、emotion_type等）

**返回值：**
- `(node_id, created, merged)`
  - `node_id`: 节点ID
  - `created`: 是否新建
  - `merged`: 是否合并

**支持的action：**
- `create`: 创建新节点
- `update`: 更新现有节点
- `merge`: 合并到现有节点

**执行流程：**
1. 如果action为 `merge` 或 `update`：
   - 更新现有节点的summary、properties
   - 合并tags和aliases
   - 生成embedding
2. 如果action为 `create`：
   - 检查是否已存在（通过name或alias）
   - 如果存在，更新；否则创建新节点
   - 生成embedding

**代码示例：**
```python
entity = {
    "name": "字节跳动",
    "action": "create",
    "summary": "互联网公司，旗下有抖音、今日头条",
    "tags": ["公司", "互联网"],
    "aliases": ["字节", "ByteDance"],
}
node_id, created, merged = await consolidator._upsert_entity(
    entity, tenant_id, user_id, unit
)
# 结果：(node_id, True, False)
```

---

### 2. _ensure_node_embedding - 生成节点Embedding

```python
async def _ensure_node_embedding(self, node_id: str, name: str, summary: str) -> None
```

**功能：** 为图谱节点生成embedding向量。

**执行流程：**
1. 检查节点是否已有embedding（查询Neo4j）
2. 如果没有，拼接 `name + summary` 作为embedding文本
3. 调用embedding API生成向量
4. 写入Neo4j节点的 `embedding` 属性

**作用：**
- 支持向量语义搜索（Retriever的路径E）
- 提高检索准确性

---

### 3. _upsert_relation - 创建关系

```python
async def _upsert_relation(
    self, rel_data: Dict[str, Any], name_to_id: Dict[str, str],
    tenant_id: str, user_id: str, unit: Dict[str, Any],
) -> bool
```

**功能：** 创建关系（如果不存在）。

**参数：**
- `rel_data`: 关系字典（包含from_name、to_name、type、description）
- `name_to_id`: 名称到节点ID的映射
- `tenant_id`: 租户ID
- `user_id`: 用户ID
- `unit`: 记忆单元

**返回值：**
- `True`: 关系创建成功
- `False`: 关系已存在或创建失败

**执行流程：**
1. 从 `name_to_id` 映射中查找from_id和to_id
2. 检查关系是否已存在
3. 如果不存在，创建新关系

---

### 4. _invalidate_relations - 失效旧关系

```python
async def _invalidate_relations(
    self,
    node_id: str,
    relation_types: List[str],
    tenant_id: str,
    user_id: str,
) -> None
```

**功能：** 标记指定类型的关系为无效（设置valid_until为当前时间）。

**使用场景：**
- 干扰检测：新信息与旧信息冲突时，失效旧关系
- 例如：用户从"美团"跳槽到"字节跳动"，失效旧的"WORKS_AT 美团"关系

---

### 5. _discover_patterns - 模式发现

```python
async def _discover_patterns(
    self, units: List[Dict[str, Any]]
) -> Tuple[List[str], List[str]]
```

**功能：** 使用LLM发现跨事件模式和冲突。

**返回值：**
- `(patterns, conflicts)`
  - `patterns`: 发现的模式列表
  - `conflicts`: 发现的冲突列表

**LLM提示词要点：**
- 分析记忆片段，识别跨事件模式、反复出现的主题或新兴趋势
- 检测冲突信息

**代码示例：**
```python
patterns, conflicts = await consolidator._discover_patterns(units)
# 结果：
# patterns = ["用户最近频繁提到跳槽", "对当前工作不满"]
# conflicts = []
```

---

### 6. _resolve_conflicts - 冲突解决

```python
async def _resolve_conflicts(self, tenant_id: str, user_id: str) -> int
```

**功能：** 扫描并解决所有带冲突标记的节点。

**执行流程：**
1. 查找所有带 `_conflict_with` 属性的节点
2. 使用LLM决定如何解决：
   - `keep_new`: 保留新信息，丢弃旧信息
   - `keep_old`: 保留旧信息，丢弃新信息
   - `keep_both`: 两者都有效，保留时间线
   - `merge`: 合并为连贯的陈述
3. 应用解决方案并清除冲突标记

**返回值：** 解决的冲突数量

---

### 7. _repair_orphans - 孤儿节点修复

```python
async def _repair_orphans(
    self, tenant_id: str, user_id: str, name_to_id: Dict[str, str]
) -> int
```

**功能：** 找出孤儿节点（无关系）并建议缺失关系。

**执行流程：**
1. 查找所有活跃节点
2. 区分孤儿节点（无关系）和已连接节点
3. 使用LLM建议孤儿节点与已连接节点之间的关系
4. 创建建议的关系

**返回值：** 创建的关系数量

**LLM提示词要点：**
- 只建议明确隐含的关系，不要猜测
- 关系类型：UPPER_SNAKE_CASE或中文
- 每个孤儿最多1个关系

---

### 8. _creative_recombination - 创造性重组

```python
async def _creative_recombination(self, tenant_id: str, user_id: str) -> int
```

**功能：** 随机组合不同记忆片段，尝试发现有价值的洞察。

**执行流程：**
1. 获取所有活跃节点，按zone分组
2. 随机抽取5-8个节点（确保多样性）
3. 使用LLM尝试发现洞察
4. 如果发现有意义的洞察，创建洞察节点
5. 创建关系：洞察节点 -[DERIVED_FROM]-> 源节点

**返回值：** 创建的洞察节点数量

**LLM提示词要点：**
- 只返回真正有价值、可操作的洞察
- 不要强行关联不相关的事物
- 洞察应具有实际帮助（副业机会、学习方向、问题解决方案等）

**代码示例：**
```python
insights = await consolidator._creative_recombination(tenant_id, user_id)
# 可能创建洞察节点：
# "洞察：用户对AI应用开发感兴趣，且正在准备跳槽，可以考虑AI创业公司的职位"
```

---

### 9. _llm_graph_review - 图谱清洁

```python
async def _llm_graph_review(self, tenant_id: str, user_id: str) -> Dict[str, int]
```

**功能：** LLM驱动的全局图谱审查和清洁。

**执行流程：**
1. 获取所有活跃节点
2. 分批发送给LLM审查（每批30个节点，最多3批）
3. LLM为每个节点决定：
   - `keep`: 无需操作
   - `merge`: 合并到另一个节点（重复）
   - `demote`: 降低重要性（低价值内容）
   - `dormant`: 标记为休眠（过时/无价值）
4. 执行操作

**返回值：**
```python
{
    "merged": int,    # 合并的节点数
    "demoted": int,   # 降级的节点数
    "dormant": int,   # 休眠的节点数
}
```

**LLM提示词要点：**
- 人物、组织、项目、计划 → 通常keep
- 同一人/事物的不同名称 → merge（如"赵禹"和"禹哥"）
- 代词节点（"我"、"用户"） → merge到用户主节点
- 纯数字、具体食物项 → demote
- 测试中的调试/技术细节 → demote或dormant

---

### 10. _infer_implicit_relations - 隐含关系推导（v3新增）

```python
async def _infer_implicit_relations(self, tenant_id: str, user_id: str) -> int
```

**功能：** 推导图谱中缺失的隐含关系。

**执行流程：**
1. 获取所有带"人物"相关标签的活跃节点
2. 获取这些人物节点之间的已有关系
3. 使用LLM推导缺失的隐含关系
4. 创建推导出的关系（只接受高置信度 >90%）

**返回值：** 新增的关系数量

**LLM提示词要点：**
- 如果A和B都是C的同事，那么A和B很可能也是同事
- 如果A是C的上级，B也是C的同事，那么A很可能也是B的上级
- 只推导高置信度（>90%）的关系
- 不要推导已经明确存在的关系

**代码示例：**
```python
# 已有关系：
# - 赵禹 -[同事]-> 张钧
# - 赵禹 -[同事]-> 梦阳
# 推导出：
# - 张钧 -[同事]-> 梦阳（置信度95%）
```

---

### 11. _check_spaced_repetition - 间隔重复检查

```python
async def _check_spaced_repetition(self, tenant_id: str, user_id: str) -> int
```

**功能：** 扫描图谱中所有active节点，找出重要但快被遗忘的记忆，标记为需要复习。

**间隔重复算法：**
- 第1次复习：1天后
- 第2次复习：3天后
- 第3次复习：7天后
- 第4次复习：21天后
- 之后每次间隔翻倍

**执行流程：**
1. 查找所有 `importance >= 6.0` 的活跃节点
2. 计算下次复习日期（基于复习次数）
3. 如果当前时间 >= 下次复习日期，标记为 `needs_review`

**返回值：** 标记为需要复习的节点数量

---

## 调用链路总览

```
定时任务（每天凌晨）
    ↓
Consolidator.consolidate()
    ↓
    ├─→ 阶段1：读取缓冲区
    │   └─→ buffer.read_unarchived()
    ├─→ 阶段2：实体与关系写入
    │   ├─→ _upsert_entity()
    │   │   ├─→ graph.update_node() / graph.create_node()
    │   │   └─→ _ensure_node_embedding() → embedding_client.get_embedding()
    │   ├─→ _upsert_relation() → graph.create_relation()
    │   └─→ _invalidate_relations() → graph.update_relation()
    ├─→ 阶段3：模式发现
    │   └─→ _discover_patterns() → LLM分析
    ├─→ 阶段4：冲突解决
    │   └─→ _resolve_conflicts() → LLM决策 → graph.update_node()
    ├─→ 阶段5：孤儿节点修复
    │   └─→ _repair_orphans() → LLM建议 → graph.create_relation()
    ├─→ 阶段6：创造性重组
    │   └─→ _creative_recombination() → LLM发现洞察 → graph.create_node()
    ├─→ 阶段7：图谱清洁
    │   └─→ _llm_graph_review() → LLM审查 → graph.merge_nodes() / graph.update_node()
    ├─→ 阶段8：隐含关系推导
    │   └─→ _infer_implicit_relations() → LLM推导 → graph.create_relation()
    ├─→ 阶段9：孤儿节点处理
    │   └─→ _handle_orphan_nodes() → graph.create_relation() / graph.update_node()
    ├─→ 阶段10：衰减与间隔重复
    │   ├─→ graph.apply_decay() → 降低检索强度
    │   └─→ _check_spaced_repetition() → 标记需要复习的记忆
    └─→ 返回统计信息
```

---

## 关键逻辑说明

### 1. 实体插入/更新/合并（action字段）
```python
# encoder返回的action字段决定操作
if action == "merge":
    # 合并到现有节点
    await graph.update_node(existing_id, updates)
    await graph.merge_tags(existing_id, tags)
    await graph.add_aliases(existing_id, aliases)
elif action == "update":
    # 更新现有节点
    await graph.update_node(existing_id, updates)
elif action == "create":
    # 创建新节点（先检查是否已存在）
    matches = await graph.find_nodes_by_name(name)
    if matches:
        # 已存在，更新
        await graph.update_node(matches[0].id, updates)
    else:
        # 不存在，创建
        await graph.create_node(node)
```

### 2. 干扰检测与关系失效
```python
# encoder检测到干扰时，返回relations_to_invalidate
relations_to_invalidate = entity.get("relations_to_invalidate", [])
if relations_to_invalidate:
    # 失效旧关系（设置valid_until为当前时间）
    await self._invalidate_relations(
        node_id, relations_to_invalidate, tenant_id, user_id
    )
```

**使用场景：**
- 用户跳槽：失效旧的"WORKS_AT"关系
- 体重变化：失效旧的"WEIGHS"关系

### 3. 节点Embedding生成
```python
# 为每个节点生成embedding向量
emb_text = f"{name}: {summary}" if summary else name
embedding = await get_embedding(emb_text, type_="db")
await graph.update_node_embedding(node_id, embedding)
```

**作用：**
- 支持向量语义搜索（Retriever的路径E）
- 提高检索准确性（尤其是模糊查询）

### 4. 创造性重组（随机组合）
```python
# 随机抽取5-8个节点（确保多样性）
selected_nodes = []
# 至少1个episodic
selected_nodes.extend(random.sample(episodic_nodes, 1))
# 至少1个semantic
selected_nodes.extend(random.sample(semantic_nodes, 1))
# 填充剩余名额
selected_nodes.extend(random.sample(all_nodes, remaining))

# 使用LLM尝试发现洞察
result = await call_llm_json(
    _CREATIVE_RECOMBINATION_SYSTEM,
    user_prompt,
    temperature=0.7  # 较高温度鼓励创造性
)
```

**设计理由：**
- 模拟人脑的创造性思维（跨领域联想）
- 随机组合增加发现新洞察的可能性
- 较高温度（0.7）鼓励LLM的创造性

### 5. LLM图谱审查（分批处理）
```python
# 分批审查（每批30个节点，最多3批）
batch_size = 30
max_batches = 3
batches = [all_nodes[i:i + batch_size] for i in range(0, len(all_nodes), batch_size)]
batches = batches[:max_batches]

for batch in batches:
    # 构建节点摘要
    nodes_json = [{"name": n.name, "tags": n.tags, ...} for n in batch]
    # LLM审查
    actions = await call_llm_json(system_prompt, user_prompt)
    # 执行操作（merge/demote/dormant）
```

**设计理由：**
- 避免一次性发送过多节点（超出LLM上下文限制）
- 限制最多3批（90个节点），平衡效果和成本

### 6. 隐含关系推导（v3新增）
```python
# 扫描人物节点及其已有关系
person_nodes = [n for n in all_nodes if any(t in person_tags for t in n.tags)]
existing_relations = [...]

# LLM推导缺失关系
result = await call_llm_json(_INFER_RELATIONS_SYSTEM, user_prompt)

# 只接受高置信度（>90%）的推导
for rel in result["inferred_relations"]:
    if rel["confidence"] >= 0.9:
        await graph.create_relation(relation)
```

**推导规则：**
- 如果A和B都是C的同事 → A和B也是同事
- 如果A是C的上级，B是C的同事 → A也是B的上级
- 只推导高置信度（>90%）的关系

---

## 使用场景

### 场景1：每日巩固（定时任务）
```python
# 每天凌晨1点执行
async def daily_consolidation():
    stats = await consolidator.consolidate(
        tenant_id="tenant_001",
        user_id="user_001",
    )
    logger.info("Daily consolidation complete: %s", stats)
```

### 场景2：手动触发巩固
```python
# 用户请求立即巩固
stats = await consolidator.consolidate(tenant_id, user_id)
return {"message": "Consolidation complete", "stats": stats}
```

---

## 注意事项

1. **重要性过滤**：importance < 3.0 的记忆单元会被跳过（但仍会归档）
2. **embedding生成**：每个节点都会生成embedding向量（支持向量搜索）
3. **干扰检测**：encoder检测到干扰时，会失效旧关系
4. **LLM成本**：图谱清洁、创造性重组、隐含关系推导都依赖LLM，成本较高
5. **分批处理**：图谱清洁分批处理（每批30个节点，最多3批）
6. **高置信度**：隐含关系推导只接受置信度 >90% 的关系

---

## 依赖关系

- **依赖：** `GraphStore`（图谱存储）、`TagDict`（标签字典）、`EncoderBuffer`（缓冲区）、`LLMClient`（LLM调用）、`EmbeddingClient`（向量嵌入）
- **被依赖：** 定时任务（每日巩固）
