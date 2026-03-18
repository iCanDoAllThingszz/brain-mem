# llm_client.py - LLM 客户端

## 文件整体功能

`llm_client.py` 提供了统一的 LLM 调用接口，支持 OpenAI 兼容的 API（如 MiniMax）。所有配置（base_url、model、api_key）可通过 `configure()` 函数注入，支持文本和 JSON 响应解析。

**核心职责：**
- 提供异步 LLM 调用接口
- 支持系统提示词和用户提示词
- 自动解析 JSON 响应（包括 markdown 代码块）
- 自动移除 `<think>...</think>` 标签（MiniMax-M2.5 等模型）
- 支持温度（temperature）和模型参数配置
- 自动从凭证文件加载 API 密钥

---

## 模块级配置

### 全局配置字典

```python
_config: Dict[str, Any] = {
    "base_url": "https://api.minimaxi.com/v1",
    "model": "MiniMax-M1",
    "api_key": "",
    "temperature": 0.3,
}
```

**说明：**
- `base_url`: OpenAI 兼容 API 的基础 URL
- `model`: 默认使用的模型名称
- `api_key`: API 密钥（可为空，会自动从环境变量或凭证文件加载）
- `temperature`: 默认采样温度（0.0-1.0）

---

### 全局客户端实例

```python
_client: Optional[AsyncOpenAI] = None
```

**说明：**
- 懒加载的 AsyncOpenAI 客户端实例
- 首次调用 `_get_client()` 时初始化
- 调用 `configure()` 后会重置，下次调用时重新初始化

---

## 核心函数

### 1. configure() - 配置 LLM 客户端

```python
def configure(
    base_url: str = None,
    model: str = None,
    api_key: str = None,
    temperature: float = None
) -> None
```

**功能：**
配置 LLM 客户端参数，必须在服务启动时调用。

**参数：**
- `base_url` (str, optional): OpenAI 兼容 API 的基础 URL
- `model` (str, optional): 模型名称
- `api_key` (str, optional): API 密钥
- `temperature` (float, optional): 默认采样温度

**关键逻辑：**
1. 更新全局 `_config` 字典
2. 重置 `_client` 为 None，强制下次调用时重新初始化
3. 记录配置日志

**调用链路：**
- 被：服务启动时调用（通常在 `main.py` 或配置加载模块）
- 调用：无

**代码示例：**
```python
from server.engine.llm_client import configure

configure(
    base_url="https://api.minimaxi.com/v1",
    model="MiniMax-M2.5",
    api_key="your_api_key",
    temperature=0.3
)
```

---

### 2. call_llm() - 调用 LLM（文本响应）

```python
async def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = None,
    model: str = None,
) -> str
```

**功能：**
调用 LLM 并返回原始文本响应。

**参数：**
- `system_prompt` (str): 系统级指令（定义模型角色和行为）
- `user_prompt` (str): 用户消息/查询
- `temperature` (float, optional): 采样温度（覆盖默认配置）
- `model` (str, optional): 模型名称（覆盖默认配置）

**返回值：**
- 模型响应的原始文本（已移除 `<think>` 标签）

**异常：**
- `RuntimeError`: API 调用失败

**关键逻辑：**
1. 调用 `_get_client()` 获取客户端实例
2. 构造消息列表：`[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]`
3. 调用 `client.chat.completions.create()`
4. 提取响应文本
5. 调用 `_strip_thinking()` 移除 `<think>` 标签
6. 返回清理后的文本

**调用链路：**
- 被：所有需要 LLM 生成文本的模块调用
- 调用：`_get_client()`, `_strip_thinking()`

**代码示例：**
```python
from server.engine.llm_client import call_llm

system = "你是一个记忆整合助手。"
user = "请总结以下对话：用户提到了减肥计划和健身目标。"
response = await call_llm(system, user, temperature=0.2)
print(response)
```

---

### 3. call_llm_json() - 调用 LLM（JSON 响应）

```python
async def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = None,
) -> Dict[str, Any]
```

**功能：**
调用 LLM 并解析响应为 JSON 字典。

**参数：**
- `system_prompt` (str): 系统级指令（应要求模型返回 JSON）
- `user_prompt` (str): 用户消息/查询
- `temperature` (float, optional): 采样温度

**返回值：**
- 解析后的 JSON 字典

**异常：**
- `ValueError`: 响应无法解析为 JSON
- `RuntimeError`: API 调用失败

**关键逻辑：**
1. 调用 `call_llm()` 获取原始文本
2. 调用 `_parse_json()` 解析 JSON
3. 返回字典

**调用链路：**
- 被：需要结构化输出的模块调用（如实体识别、关系提取）
- 调用：`call_llm()`, `_parse_json()`

**代码示例：**
```python
from server.engine.llm_client import call_llm_json

system = "你是一个实体识别助手。返回 JSON 格式：{\"entities\": [{\"name\": \"...\", \"type\": \"...\"}]}"
user = "用户提到了禹哥和减肥计划。"
result = await call_llm_json(system, user, temperature=0.1)
print(result["entities"])
```

---

## 内部辅助函数

### 4. _get_client() - 获取客户端实例

```python
def _get_client() -> AsyncOpenAI
```

**功能：**
懒加载并返回共享的 AsyncOpenAI 客户端实例。

**关键逻辑：**
1. 如果 `_client` 已存在，直接返回
2. 否则，初始化新客户端：
   - 从 `_config["api_key"]` 获取 API 密钥
   - 如果为空，尝试从环境变量 `MINIMAX_API_KEY` 获取
   - 如果仍为空，尝试从凭证文件 `~/.openclaw/workspace/credentials/minimax_api.json` 加载
   - 使用 `_config["base_url"]` 和 API 密钥创建 `AsyncOpenAI` 实例
3. 返回客户端实例

**调用链路：**
- 被：`call_llm()` 调用
- 调用：`AsyncOpenAI()`

**凭证文件格式：**
```json
{
  "minimax_api_key": "your_api_key_here"
}
```

---

### 5. _strip_thinking() - 移除思考标签

```python
def _strip_thinking(text: str) -> str
```

**功能：**
移除 LLM 输出中的 `<think>...</think>` 标签（某些模型如 MiniMax-M2.5 会输出思考过程）。

**参数：**
- `text` (str): 原始 LLM 响应文本

**返回值：**
- 清理后的文本

**关键逻辑：**
使用正则表达式 `r"<think>[\s\S]*?</think>\s*"` 匹配并移除所有 `<think>` 块。

**调用链路：**
- 被：`call_llm()` 调用
- 调用：`re.sub()`

**代码示例：**
```python
raw = "<think>我需要先分析...</think>用户提到了减肥计划。"
clean = _strip_thinking(raw)
print(clean)  # 输出：用户提到了减肥计划。
```

---

### 6. _parse_json() - 解析 JSON

```python
def _parse_json(raw: str) -> Dict[str, Any]
```

**功能：**
鲁棒地解析 JSON 字符串，支持 markdown 代码块包裹的 JSON。

**参数：**
- `raw` (str): 原始字符串（可能包含 markdown 代码块）

**返回值：**
- 解析后的字典

**异常：**
- `ValueError`: 无法解析为 JSON

**关键逻辑：**
1. 去除首尾空白
2. 尝试匹配 markdown 代码块：`` ```json ... ``` `` 或 `` ``` ... ``` ``
3. 如果匹配成功，提取代码块内容
4. 尝试解析 JSON
5. 如果失败，尝试提取第一个 `{...}` 或 `[...]` 块
6. 如果仍失败，抛出 `ValueError`

**调用链路：**
- 被：`call_llm_json()` 调用
- 调用：`json.loads()`, `re.search()`

**代码示例：**
```python
raw = '''
```json
{
  "entities": [
    {"name": "禹哥", "type": "人物"}
  ]
}
```
'''
result = _parse_json(raw)
print(result["entities"])
```

---

## 调用链路总览

```
服务启动
  → configure()
    → 更新 _config
    → 重置 _client

LLM 文本调用
  → call_llm()
    → _get_client()
      → AsyncOpenAI()
      → [从凭证文件加载 API 密钥]
    → client.chat.completions.create()
    → _strip_thinking()
    → 返回文本

LLM JSON 调用
  → call_llm_json()
    → call_llm()
      → _get_client()
      → client.chat.completions.create()
      → _strip_thinking()
    → _parse_json()
      → json.loads()
      → re.search()
    → 返回字典
```

---

## 重要注意事项

1. **配置优先级**：
   - 函数参数（temperature, model）> 全局配置（_config）
   - API 密钥加载顺序：函数参数 > 环境变量 > 凭证文件

2. **异步调用**：
   - 所有 LLM 调用都是异步的，必须使用 `await`

3. **错误处理**：
   - API 调用失败会抛出 `RuntimeError`
   - JSON 解析失败会抛出 `ValueError`
   - 调用方需要捕获异常并处理

4. **思考标签**：
   - MiniMax-M2.5 等模型会输出 `<think>` 标签
   - 自动移除，不影响最终结果

5. **JSON 解析**：
   - 支持 markdown 代码块包裹的 JSON
   - 支持提取第一个 JSON 对象/数组
   - 鲁棒性强，适应不同模型的输出格式

6. **凭证安全**：
   - API 密钥存储在 `~/.openclaw/workspace/credentials/minimax_api.json`
   - 不要将凭证文件提交到版本控制

7. **模型兼容性**：
   - 支持所有 OpenAI 兼容的 API
   - 只需修改 `base_url` 和 `model` 即可切换模型

---

## 使用示例

### 示例 1：配置客户端

```python
from server.engine.llm_client import configure

# 服务启动时配置
configure(
    base_url="https://api.minimaxi.com/v1",
    model="MiniMax-M2.5",
    temperature=0.3
)
```

---

### 示例 2：文本生成

```python
from server.engine.llm_client import call_llm

async def summarize_conversation(messages: list) -> str:
    system = "你是一个对话总结助手。"
    user = f"请总结以下对话：\n{messages}"
    summary = await call_llm(system, user, temperature=0.2)
    return summary
```

---

### 示例 3：结构化输出

```python
from server.engine.llm_client import call_llm_json

async def extract_entities(text: str) -> list:
    system = """
    你是一个实体识别助手。
    返回 JSON 格式：{"entities": [{"name": "...", "type": "..."}]}
    """
    user = f"文本：{text}"
    result = await call_llm_json(system, user, temperature=0.1)
    return result.get("entities", [])
```

---

### 示例 4：自定义模型

```python
from server.engine.llm_client import call_llm

async def creative_writing(prompt: str) -> str:
    system = "你是一个创意写作助手。"
    # 使用更高的温度和不同的模型
    response = await call_llm(
        system,
        prompt,
        temperature=0.8,
        model="MiniMax-M1"
    )
    return response
```

---

## 性能优化建议

1. **客户端复用**：
   - 客户端实例是全局共享的，避免重复创建

2. **温度调优**：
   - 事实性任务（实体识别、总结）：temperature=0.1-0.3
   - 创意性任务（写作、对话）：temperature=0.5-0.8

3. **超时处理**：
   - 考虑为 API 调用添加超时机制（AsyncOpenAI 支持 timeout 参数）

4. **重试机制**：
   - 对于临时性错误（网络波动），可添加重试逻辑

5. **批量调用**：
   - 如需批量处理，考虑使用 `asyncio.gather()` 并发调用

6. **缓存结果**：
   - 对于相同的输入，可缓存 LLM 响应（需注意缓存失效策略）
