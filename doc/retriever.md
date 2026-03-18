# retriever.py - 记忆检索器

## 文件整体功能

`Retriever` 是 brain-memory 服务的多路径记忆检索器，对应人脑的记忆召回机制。

**核心职责：**
- 多路径检索：精确名称、别名、模糊匹配、关系遍历、向量语义搜索
- 候选评分：综合相关性、重要性、时效性、访问频率、情绪共鸣
- LLM重构：将记忆片段合成为连贯的上下文
- 访问记录更新：更新检索强度、访问计数、别名学习、间隔重复

**设计理念：**
- 模拟人脑的多路径记忆召回（联想、线索、情绪触发）
- 综合评分机制（不仅仅是关键词匹配）
- 自适应学习（别名学习、间隔重复）

---

## 类：Retriever

### 作用
多路径记忆检索器，实现记忆召回机制。

### 类属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `_query_cache` | Dict[tuple, tuple] | 查询缓存：(session_id, query_hash) → (result, timestamp) |
| `_CACHE_TTL_SECONDS` | int | 缓存TTL：10秒 |

### 初始化方法

```python
def __init__(self, graph: GraphStore, buffer: EncoderBuffer) -> None
```

**参数：**
- `graph`: GraphStore 实例，用于图谱检索
- `buffer`: EncoderBuffer 实例，用于缓冲区检索

---

## 核心方法

### 1. retrieve - 多路径检索

```python
async def retrieve(
    self,
    query: str,
    tenant_id: str,
    user_id: str,
    working_memory: Optional[Dict[str, Any]] = None,
    max_results: int = 10,
    session_id: Optional[str] = None,
) -> Dict[str, Any]
```

**功能：** 使用多路径搜索检索与查询相关的记忆。

**参数：**
- `query`: 自然语言查询字符串
- `tenant_id`: 租户ID
- `user_id`: 用户ID
- `working_memory`: 可选的会话上下文（用于评分）
- `max_results`: 最多返回的记忆片段数量（默认10）
- `session_id`: 可选的会话ID（用于缓存）

**返回值：**
```python
{
    "context": str,  # 自然语言上下文（可直接注入LLM prompt）
    "memories": [
        {
            "id": str,
            "content": str,
            "relevance": float,  # 相关性评分（0-1）
            "confidence": float  # 置信度（0-1）
        },
        ...
    ]
}
```

**执行流程（10步）：**

1. **查询缓存检查**：如果10秒内有相同查询，直接返回缓存结果
2. **提取搜索线索**：使用LLM从查询中提取实体、关键词、时间提示、情绪
3. **路径A：精确名称匹配** → `find_nodes_by_name()`
4. **路径B：别名匹配** → `find_nodes_by_alias()`
5. **路径C：模糊关键词匹配** → `find_nodes_fuzzy()`
6. **路径D：休眠节点搜索** → `find_dormant_nodes()`（用于复活）
7. **路径E：向量语义搜索** → Neo4j向量索引 + Buffer向量搜索
8. **关系遍历**：从匹配节点出发，遍历1-2跳关系
9. **缓冲区检索**：获取最近20条未归档的记忆单元
10. **综合评分与排序**：
    - 相关性（0.4-0.5）
    - 重要性（0.15）
    - 时效性（0.15）
    - 访问频率（0.1）
    - 情绪共鸣（0.1-0.2）
11. **最低分数阈值过滤**：score >= 0.25
12. **LLM重构上下文**：将top-K片段合成为连贯的事实性摘要
13. **更新访问记录**：增加访问计数、更新检索强度、别名学习、间隔重复

**代码示例：**
```python
# 检索记忆
result = await retriever.retrieve(
    query="我上次面试字节跳动怎么样？",
    tenant_id="tenant_001",
    user_id="user_001",
    max_results=5,
)
# 结果：
# {
#     "context": "上次字节跳动一面通过了算法题，但系统设计部分需要改进。面试官建议多练习分布式系统设计。",
#     "memories": [
#         {
#             "id": "node_123",
#             "content": "字节跳动一面：算法题通过，系统设计待改进",
#             "relevance": 0.85,
#             "confidence": 1.0
#         },
#         ...
#     ]
# }
```

**调用链路：**
- 被调用：API层（每次用户查询）
- 调用：
  - `self._extract_clues()` → LLM提取线索
  - `self._search_by_name()` → 精确名称搜索
  - `self._search_by_alias()` → 别名搜索
  - `self._search_fuzzy()` → 模糊搜索
  - `self.graph.find_dormant_nodes()` → 休眠节点搜索
  - `self.graph.vector_search()` → 向量搜索
  - `self._traverse()` → 关系遍历
  - `self.buffer.read_recent()` → 缓冲区检索
  - `self._score_candidates()` → 综合评分
  - `self._reconstruct_context()` → LLM重构上下文
  - `self._update_access_batch()` → 批量更新访问记录

---

## 内部辅助方法

### 1. _extract_clues - 提取搜索线索

```python
async def _extract_clues(self, query: str) -> Dict[str, Any]
```

**功能：** 使用LLM从查询中提取实体、关键词、时间提示、情绪。

**返回值：**
```python
{
    "entities": ["实体名1", "实体名2"],
    "keywords": ["关键词1", "关键词2"],
    "time_hint": "today|recent|specific_date|none",
    "query_intent": "用一句话描述用户想知道什么",
    "query_emotion": "joy|sadness|anger|fear|surprise|neutral"
}
```

**LLM提示词要点：**
- 只提取有意义的实体和关键词（不提取停用词）
- 实体应该是专有名词（人名、地名、项目名）
- 关键词应该有区分度（动词、名词、形容词）
- 识别查询中的情感信息
- 如果是纯社交性质（如"嗯嗯"、"好的"），返回空列表

---

### 2. _score_candidates - 综合评分

```python
def _score_candidates(
    self,
    nodes: list,
    buffer_units: List[Dict[str, Any]],
    query: str,
    entities: List[str],
    keywords: List[str],
    current_emotion: str = "neutral",
) -> List[Dict[str, Any]]
```

**功能：** 对图谱节点和缓冲区单元进行综合评分并排序。

**评分公式：**
```python
# 当前情绪为neutral时：
score = relevance×0.5 + importance×0.15 + recency×0.15 + access_freq×0.1 + emotional×0.1

# 当前情绪为非neutral时（情绪共鸣权重提升）：
score = relevance×0.4 + importance×0.15 + recency×0.15 + access_freq×0.1 + emotional×0.2
```

**评分维度：**

| 维度 | 计算方法 | 权重 |
|------|---------|------|
| 相关性（relevance） | 关键词匹配度（精确匹配、部分匹配、查询词重叠） | 0.4-0.5 |
| 重要性（importance） | 节点importance属性 / 10.0 | 0.15 |
| 时效性（recency） | 1.0 - (天数 / 30.0)，30天内线性衰减 | 0.15 |
| 访问频率（access_freq） | 节点access_count / 100.0 | 0.1 |
| 情绪共鸣（emotional） | 节点情绪与当前情绪的匹配度 | 0.1-0.2 |

**返回值：**
```python
[
    {
        "id": str,
        "content": str,
        "score": float,
        "confidence": float,
        "source": "graph" | "buffer"
    },
    ...
]
```

---

### 3. _text_relevance - 文本相关性评分

```python
@staticmethod
def _text_relevance(text: str, query: str, entities: List[str], keywords: List[str]) -> float
```

**功能：** 增强的关键词相关性评分（0-1）。

**匹配策略（三层）：**
1. **精确匹配**（权重0.6）：实体/关键词完全出现在文本中
2. **部分匹配**（权重0.2）：2+字符的子串匹配
3. **查询词重叠**（权重0.2）：查询分词后的词汇匹配

**代码示例：**
```python
relevance = _text_relevance(
    text="字节跳动一面：算法题通过，系统设计待改进",
    query="我上次面试字节跳动怎么样？",
    entities=["字节跳动"],
    keywords=["面试", "算法", "系统设计"]
)
# 结果：0.85（高相关性）
```

---

### 4. _emotional_resonance - 情绪共鸣评分

```python
@staticmethod
def _emotional_resonance(emotional_tag: Any, current_emotion: str) -> float
```

**功能：** 计算节点情绪与当前情绪的共鸣度（0-1）。

**规则：**
1. **精确匹配**：相同情绪类型 → 共鸣度 = intensity × 1.0
2. **同价态**：都是正面或都是负面 → 共鸣度 = intensity × 0.7
3. **特殊规则**：用户负面情绪时，高强度正面记忆（鼓励性）→ 共鸣度 = intensity × 0.5
4. **相反价态**：正负相反 → 共鸣度 = intensity × 0.2

**情绪分类：**
- 正面情绪：`joy`、`surprise`
- 负面情绪：`sadness`、`anger`、`fear`

**代码示例：**
```python
# 用户当前情绪：sadness（负面）
# 节点情绪：joy（正面），强度8
resonance = _emotional_resonance(
    emotional_tag={"type": "joy", "intensity": 8},
    current_emotion="sadness"
)
# 结果：0.4（特殊规则：负面情绪时，正面记忆有鼓励作用）
```

---

### 5. _reconstruct_context - LLM重构上下文

```python
async def _reconstruct_context(
    self, query: str, candidates: List[Dict[str, Any]]
) -> str
```

**功能：** 使用LLM将top-K记忆片段合成为连贯的事实性摘要。

**LLM提示词要点：**
- 只输出事实性记忆内容，不要回答用户的问题
- 不要提供分析、建议或评论
- 不要直接称呼用户（不要用"你"、"your"）
- 简洁——只包含能提供新信息的事实（目标50-100字）
- 使用自然语言，不要用项目符号
- 如果记忆相互矛盾，注明矛盾之处
- 如果记忆稀疏或不相关，返回"No relevant memories found."
- 用中文书写
- 如果记忆片段都是关于当前正在讨论的话题，返回"No relevant memories found."

**代码示例：**
```python
context = await self._reconstruct_context(
    query="我上次面试字节跳动怎么样？",
    candidates=[
        {"content": "字节跳动一面：算法题通过，系统设计待改进"},
        {"content": "面试官建议多练习分布式系统设计"},
    ]
)
# 结果：
# "上次字节跳动一面通过了算法题，但系统设计部分需要改进。面试官建议多练习分布式系统设计。"
```

---

### 6. _update_access_batch - 批量更新访问记录

```python
async def _update_access_batch(self, node_ids: List[str], fuzzy_matches: Dict[str, str]) -> None
```

**功能：** 批量更新检索到的节点的访问记录。

**更新内容：**
1. **访问计数**：`access_count += 1`
2. **最后访问时间**：`last_accessed = now`
3. **检索强度**：`retrieval_strength += 0.1`（最大10.0）
4. **别名学习**：如果通过模糊匹配找到，将查询词添加为别名
5. **间隔重复**：如果节点标记为 `needs_review`，清除标记并更新复习历史
6. **休眠节点复活**：如果节点状态为 `dormant`，复活为 `active`

**调用链路：**
- 被调用：`retrieve()`
- 调用：
  - `self._update_and_revive()` → 更新单个节点
    - `self.graph.get_node()` → 获取节点
    - `self.graph.update_access()` → 更新访问记录
    - `self.graph.update_node()` → 更新别名/复习历史
    - `self.graph.revive_if_dormant()` → 复活休眠节点

---

### 7. _retrieve_with_fallback - 补偿检索

```python
async def _retrieve_with_fallback(
    self,
    query: str,
    entities: List[str],
    keywords: List[str],
    current_emotion: str,
    tenant_id: str,
    user_id: str,
    max_results: int,
) -> List[Dict[str, Any]]
```

**功能：** 当正常检索失败时，尝试更宽松的检索条件。

**补偿策略（按顺序尝试）：**
1. **降低分数阈值**：从0.25降到0.15
2. **扩大遍历深度**：从2跳扩展到3跳
3. **放宽关键词匹配**：使用更短的子串（2-3字符）

**返回值：**
- 补偿检索的候选列表（confidence标记为0.5）

---

## 调用链路总览

```
API层（用户查询）
    ↓
Retriever.retrieve()
    ↓
    ├─→ 查询缓存检查
    ├─→ _extract_clues() → LLM提取线索
    ├─→ 多路径并行检索：
    │   ├─→ _search_by_name() → GraphStore.find_nodes_by_name()
    │   ├─→ _search_by_alias() → GraphStore.find_nodes_by_alias()
    │   ├─→ _search_fuzzy() → GraphStore.find_nodes_fuzzy()
    │   ├─→ GraphStore.find_dormant_nodes() → 休眠节点搜索
    │   └─→ GraphStore.vector_search() → 向量语义搜索
    ├─→ _traverse() → GraphStore.traverse_relations() → 关系遍历
    ├─→ buffer.read_recent() → 缓冲区检索
    ├─→ _score_candidates() → 综合评分
    │   ├─→ _text_relevance() → 文本相关性
    │   ├─→ _recency_score() → 时效性
    │   └─→ _emotional_resonance() → 情绪共鸣
    ├─→ 最低分数阈值过滤（0.25）
    ├─→ _reconstruct_context() → LLM重构上下文
    └─→ _update_access_batch() → 批量更新访问记录
            └─→ _update_and_revive()
                    ├─→ GraphStore.update_access() → 更新访问
                    ├─→ GraphStore.update_node() → 别名学习/复习历史
                    └─→ GraphStore.revive_if_dormant() → 复活休眠节点
```

---

## 关键逻辑说明

### 1. 多路径检索（5条路径）
```python
# 路径A：精确名称匹配
nodes_a = await graph.find_nodes_by_name("字节跳动")

# 路径B：别名匹配
nodes_b = await graph.find_nodes_by_alias("字节")

# 路径C：模糊关键词匹配
nodes_c = await graph.find_nodes_fuzzy("面试")

# 路径D：休眠节点搜索（用于复活）
nodes_d = await graph.find_dormant_nodes(["字节跳动", "面试"])

# 路径E：向量语义搜索
query_embedding = await get_embedding(query)
nodes_e = await graph.vector_search(query_embedding, top_k=5)
```

**设计理由：**
- 模拟人脑的多路径记忆召回（联想、线索、情绪触发）
- 提高召回率（不同路径可能找到不同的相关记忆）
- 支持模糊查询（用户可能记不清确切名称）

### 2. 综合评分机制
```python
# 情绪为neutral时
score = relevance×0.5 + importance×0.15 + recency×0.15 + access_freq×0.1 + emotional×0.1

# 情绪为非neutral时（情绪共鸣权重提升）
score = relevance×0.4 + importance×0.15 + recency×0.15 + access_freq×0.1 + emotional×0.2
```

**设计理由：**
- 相关性最重要（0.4-0.5）
- 重要性和时效性次之（各0.15）
- 访问频率和情绪共鸣作为辅助（0.1-0.2）
- 情绪状态下，情绪共鸣权重提升（0.1→0.2）

### 3. 别名学习（Alias Learning）
```python
# 如果通过模糊匹配找到节点
if fuzzy_term and fuzzy_term not in node.aliases:
    # 将查询词添加为别名
    new_aliases = node.aliases + [fuzzy_term]
    await graph.update_node(node.id, {"aliases": new_aliases})
```

**作用：**
- 自适应学习用户的表达习惯
- 下次查询时可以通过别名直接匹配（路径B）
- 提高检索效率

### 4. 间隔重复（Spaced Repetition）
```python
# 如果节点标记为needs_review
if node.properties.get("needs_review"):
    # 清除标记
    # 更新复习历史
    review_count += 1
    next_review_date = now + timedelta(days=interval_days)
    await graph.update_node(node.id, {
        "properties": {
            "needs_review": False,
            "review_count": review_count,
            "last_review_date": now,
            "next_review_date": next_review_date,
        }
    })
```

**间隔算法：**
- 第1次复习：1天后
- 第2次复习：3天后
- 第3次复习：7天后
- 第4次复习：21天后
- 之后每次间隔翻倍

### 5. 查询缓存（10秒TTL）
```python
# 缓存key：(session_id, query_hash)
cache_key = (session_id, hashlib.md5(query.encode()).hexdigest())

# 检查缓存
if cache_key in _query_cache:
    cached_result, cached_time = _query_cache[cache_key]
    if (now - cached_time).total_seconds() < 10:
        return cached_result  # 命中缓存
```

**设计理由：**
- 避免短时间内重复查询（如用户连续发送相同问题）
- 减少LLM调用和图谱查询
- TTL设置为10秒（平衡缓存命中率和数据新鲜度）

---

## 使用场景

### 场景1：用户查询历史事件
```python
result = await retriever.retrieve(
    query="我上次面试字节跳动怎么样？",
    tenant_id="tenant_001",
    user_id="user_001",
)
# 返回：上次面试的详细记录
```

### 场景2：情绪触发的记忆召回
```python
result = await retriever.retrieve(
    query="我今天心情不好",
    tenant_id="tenant_001",
    user_id="user_001",
    working_memory={"emotional_baseline": "negative"},
)
# 返回：可能包含鼓励性的正面记忆（情绪共鸣机制）
```

### 场景3：模糊查询
```python
result = await retriever.retrieve(
    query="那个什么跳动的公司",
    tenant_id="tenant_001",
    user_id="user_001",
)
# 通过模糊匹配找到"字节跳动"
# 并将"跳动"添加为别名（别名学习）
```

---

## 注意事项

1. **查询缓存**：10秒内相同查询直接返回缓存（避免重复调用）
2. **最低分数阈值**：score < 0.25 的候选会被过滤（确保质量）
3. **补偿检索**：正常检索失败时自动触发（降低阈值、扩大遍历）
4. **别名学习**：模糊匹配成功后自动添加别名（自适应学习）
5. **间隔重复**：检索时自动更新复习历史（记忆强化）
6. **休眠节点复活**：检索到休眠节点时自动复活（记忆恢复）

---

## 依赖关系

- **依赖：** `GraphStore`（图谱存储）、`EncoderBuffer`（缓冲区）、`LLMClient`（LLM调用）、`EmbeddingClient`（向量嵌入）
- **被依赖：** API层（用户查询处理）
