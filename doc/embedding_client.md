# embedding_client.py - 嵌入向量客户端

## 文件整体功能

`embedding_client.py` 提供了基于 MiniMax Embedding API 的异步文本嵌入生成服务，支持 LRU 缓存以提高性能。

**核心职责：**
- 调用 MiniMax Embedding API 生成 1536 维向量
- 支持单文本和批量文本嵌入
- 提供 LRU 缓存机制（最多缓存 1000 个嵌入）
- 支持两种嵌入类型：`query`（检索）和 `db`（存储）
- 自动从凭证文件或环境变量加载 API 密钥
- 失败时返回零向量作为降级方案

---

## 模块级配置

### 常量定义

```python
_MAX_CACHE = 1000  # LRU 缓存最大容量
_API_URL = "https://api.minimaxi.com/v1/embeddings"  # MiniMax Embedding API 端点
_MODEL = "embo-01"  # 嵌入模型名称
DIMENSION = 1536  # 嵌入向量维度
```

---

### 全局变量

```python
_api_key: Optional[str] = None  # API 密钥（懒加载）
_cache: OrderedDict = OrderedDict()  # LRU 缓存（有序字典）
```

**说明：**
- `_api_key`: 首次调用时从凭证文件或环境变量加载
- `_cache`: 使用 `OrderedDict` 实现 LRU 缓存，键为 `_cache_key()` 生成的哈希值

---

## 核心函数

### 1. get_embedding() - 获取单文本嵌入

```python
async def get_embedding(text: str, type_: str = "query") -> List[float]
```

**功能：**
为单个文本生成嵌入向量，支持缓存。

**参数：**
- `text` (str): 输入文本
- `type_` (str): 嵌入类型，可选值：
  - `"query"`: 用于检索查询（默认）
  - `"db"`: 用于数据库存储

**返回值：**
- 1536 维浮点数列表

**关键逻辑：**
1. 生成缓存键：`_cache_key(text, type_)`
2. 检查缓存：
   - 如果命中，将该键移到末尾（LRU 更新）并返回缓存值
3. 如果未命中：
   - 调用 `get_embeddings([text], type_)` 批量接口
   - 将结果存入缓存
   - 如果缓存超过 `_MAX_CACHE`，移除最旧的条目
4. 返回嵌入向量

**调用链路：**
- 被：单文本嵌入场景调用（如实时查询）
- 调用：`_cache_key()`, `get_embeddings()`

**代码示例：**
```python
from server.engine.embedding_client import get_embedding

# 查询嵌入
query_vec = await get_embedding("减肥计划", type_="query")
print(len(query_vec))  # 输出：1536

# 存储嵌入
db_vec = await get_embedding("减肥计划", type_="db")
```

---

### 2. get_embeddings() - 批量获取嵌入

```python
async def get_embeddings(texts: List[str], type_: str = "db") -> List[List[float]]
```

**功能：**
批量生成嵌入向量，一次 API 调用处理多个文本。

**参数：**
- `texts` (List[str]): 文本列表
- `type_` (str): 嵌入类型（`"query"` 或 `"db"`，默认 `"db"`）

**返回值：**
- 嵌入向量列表，每个向量为 1536 维浮点数列表

**关键逻辑：**
1. 如果 `texts` 为空，返回空列表
2. 调用 `_get_api_key()` 获取 API 密钥
3. 如果没有 API 密钥，返回零向量列表（降级方案）
4. 使用 `httpx.AsyncClient` 发送 POST 请求到 MiniMax API：
   - 请求头：`Authorization: Bearer {api_key}`, `Content-Type: application/json`
   - 请求体：`{"model": "embo-01", "texts": texts, "type": type_}`
5. 解析响应：
   - 成功（200）：提取 `vectors` 字段并返回
   - 失败：记录错误日志，返回零向量列表
6. 异常处理：捕获所有异常，返回零向量列表

**调用链路：**
- 被：批量嵌入场景调用（如批量索引）
- 调用：`_get_api_key()`, `httpx.AsyncClient.post()`

**代码示例：**
```python
from server.engine.embedding_client import get_embeddings

texts = ["减肥计划", "健身目标", "饮食控制"]
vectors = await get_embeddings(texts, type_="db")
print(len(vectors))  # 输出：3
print(len(vectors[0]))  # 输出：1536
```

---

## 内部辅助函数

### 3. _get_api_key() - 获取 API 密钥

```python
def _get_api_key() -> str
```

**功能：**
懒加载 API 密钥，优先级：缓存 > 凭证文件 > 环境变量。

**返回值：**
- API 密钥字符串（可能为空）

**关键逻辑：**
1. 如果 `_api_key` 已缓存，直接返回
2. 尝试从凭证文件加载：
   - 路径：`~/.openclaw/workspace/credentials/minimax_api.json`
   - 字段：`minimax_api_key`
3. 如果凭证文件不存在或字段为空，尝试从环境变量 `MINIMAX_API_KEY` 加载
4. 缓存并返回 API 密钥

**调用链路：**
- 被：`get_embeddings()` 调用
- 调用：`os.path.exists()`, `json.load()`, `os.getenv()`

**凭证文件格式：**
```json
{
  "minimax_api_key": "your_api_key_here"
}
```

---

### 4. _cache_key() - 生成缓存键

```python
def _cache_key(text: str, type_: str) -> str
```

**功能：**
为文本和类型生成唯一的缓存键（MD5 哈希）。

**参数：**
- `text` (str): 输入文本
- `type_` (str): 嵌入类型

**返回值：**
- 32 字符的 MD5 哈希字符串

**关键逻辑：**
1. 拼接字符串：`"{type_}:{text}"`
2. 计算 MD5 哈希
3. 返回十六进制字符串

**调用链路：**
- 被：`get_embedding()` 调用
- 调用：`hashlib.md5()`

**代码示例：**
```python
key1 = _cache_key("减肥计划", "query")
key2 = _cache_key("减肥计划", "db")
print(key1 != key2)  # 输出：True（不同类型生成不同键）
```

---

## 调用链路总览

```
单文本嵌入
  → get_embedding()
    → _cache_key()
    → [检查缓存]
    → get_embeddings()
      → _get_api_key()
        → [从凭证文件或环境变量加载]
      → httpx.AsyncClient.post()
      → [解析响应]
    → [更新缓存]
    → 返回向量

批量嵌入
  → get_embeddings()
    → _get_api_key()
      → [从凭证文件或环境变量加载]
    → httpx.AsyncClient.post()
    → [解析响应]
    → 返回向量列表
```

---

## 重要注意事项

1. **嵌入类型**：
   - `"query"`: 用于检索查询，优化召回率
   - `"db"`: 用于数据库存储，优化存储效率
   - 同一文本的两种类型嵌入不同，需分别缓存

2. **缓存机制**：
   - LRU 缓存，最多存储 1000 个嵌入
   - 缓存键包含文本和类型，确保唯一性
   - 缓存命中时会更新访问顺序（移到末尾）

3. **降级方案**：
   - 如果 API 密钥缺失或 API 调用失败，返回零向量 `[0.0] * 1536`
   - 零向量不会影响系统运行，但会导致相似度计算失效

4. **异步调用**：
   - 所有函数都是异步的，必须使用 `await`
   - 使用 `httpx.AsyncClient` 进行异步 HTTP 请求

5. **超时设置**：
   - `httpx.AsyncClient(timeout=30)` 设置 30 秒超时
   - 避免长时间等待导致系统阻塞

6. **错误处理**：
   - API 错误（非 200 状态码）：记录日志，返回零向量
   - 网络异常：捕获异常，返回零向量
   - 响应格式错误：记录日志，返回零向量

7. **批量优化**：
   - 批量调用比单次调用更高效（减少 API 请求次数）
   - 建议批量处理文本（如批量索引节点）

8. **向量维度**：
   - 固定为 1536 维（MiniMax embo-01 模型）
   - 与 Neo4j 向量索引配置一致

---

## 使用示例

### 示例 1：单文本嵌入（查询）

```python
from server.engine.embedding_client import get_embedding

async def search_similar_nodes(query: str):
    # 生成查询嵌入
    query_vec = await get_embedding(query, type_="query")
    
    # 使用向量检索
    results = await graph.vector_search(query_vec, top_k=10)
    return results
```

---

### 示例 2：批量嵌入（存储）

```python
from server.engine.embedding_client import get_embeddings

async def index_nodes(nodes: list):
    # 提取节点文本
    texts = [f"{node.name}: {node.summary}" for node in nodes]
    
    # 批量生成嵌入
    vectors = await get_embeddings(texts, type_="db")
    
    # 更新节点嵌入
    for node, vec in zip(nodes, vectors):
        await graph.update_node_embedding(node.id, vec)
```

---

### 示例 3：缓存效果测试

```python
from server.engine.embedding_client import get_embedding
import time

async def test_cache():
    text = "减肥计划"
    
    # 第一次调用（API 请求）
    start = time.time()
    vec1 = await get_embedding(text, type_="query")
    print(f"第一次调用耗时：{time.time() - start:.3f}s")
    
    # 第二次调用（缓存命中）
    start = time.time()
    vec2 = await get_embedding(text, type_="query")
    print(f"第二次调用耗时：{time.time() - start:.3f}s")
    
    # 验证结果一致
    assert vec1 == vec2
```

---

### 示例 4：错误处理

```python
from server.engine.embedding_client import get_embeddings

async def safe_embed(texts: list) -> list:
    try:
        vectors = await get_embeddings(texts, type_="db")
        
        # 检查是否为零向量（降级）
        if all(v == [0.0] * 1536 for v in vectors):
            logger.warning("嵌入生成失败，使用零向量")
        
        return vectors
    except Exception as e:
        logger.error(f"嵌入生成异常：{e}")
        return [[0.0] * 1536] * len(texts)
```

---

## 性能优化建议

1. **批量处理**：
   - 尽量使用 `get_embeddings()` 批量处理
   - 减少 API 请求次数，提高吞吐量

2. **缓存利用**：
   - 对于高频查询文本，缓存命中率高
   - 考虑增加 `_MAX_CACHE` 容量（需权衡内存占用）

3. **并发控制**：
   - 使用 `asyncio.Semaphore` 限制并发 API 请求数
   - 避免触发 API 速率限制

4. **预计算嵌入**：
   - 对于静态文本（如节点摘要），提前计算并存储嵌入
   - 避免重复计算

5. **降级策略**：
   - 零向量降级方案适合开发环境
   - 生产环境建议添加告警和重试机制

6. **监控指标**：
   - 缓存命中率
   - API 调用延迟
   - 失败率

---

## API 请求格式

### 请求示例

```http
POST https://api.minimaxi.com/v1/embeddings
Authorization: Bearer {api_key}
Content-Type: application/json

{
  "model": "embo-01",
  "texts": ["减肥计划", "健身目标"],
  "type": "db"
}
```

### 响应示例

```json
{
  "vectors": [
    [0.123, -0.456, 0.789, ...],  // 1536 维
    [0.234, -0.567, 0.890, ...]   // 1536 维
  ]
}
```

---

## 常见问题

### Q1: 为什么需要两种嵌入类型？

**A:** 
- `"query"` 类型优化召回率，适合检索查询
- `"db"` 类型优化存储效率，适合数据库索引
- 两种类型的嵌入向量不同，不能混用

### Q2: 缓存会占用多少内存？

**A:**
- 每个嵌入向量：1536 × 8 字节（float64）≈ 12 KB
- 1000 个缓存条目：约 12 MB
- 可根据实际内存情况调整 `_MAX_CACHE`

### Q3: API 调用失败怎么办？

**A:**
- 自动返回零向量作为降级方案
- 建议添加重试机制和告警
- 检查 API 密钥和网络连接

### Q4: 如何提高嵌入生成速度？

**A:**
1. 使用批量接口 `get_embeddings()`
2. 利用缓存机制
3. 预计算静态文本的嵌入
4. 使用并发控制（`asyncio.gather()`）

### Q5: 嵌入向量可以持久化吗？

**A:**
- 可以，存储在 Neo4j 节点的 `embedding` 属性中
- 也可以存储在 SQLite 的 `embedding` 字段（BLOB 类型）
- 建议使用二进制格式（如 `numpy.array.tobytes()`）减少存储空间
