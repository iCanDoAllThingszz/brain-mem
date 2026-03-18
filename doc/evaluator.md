# evaluator.py - 评估器引擎

## 文件整体功能

`evaluator.py` 是 Brain Memory Service 的记忆价值评估器，对应人脑的**前额叶皮层 + 杏仁核**。它负责：

1. **深度评估**：对消息的记忆价值进行三维度评分（任务相关性、情绪强度、新颖性）
2. **编码决策**：基于评分决定是否编码到长期记忆
3. **优先级分配**：为决定编码的消息分配优先级（high/medium/low）
4. **上下文感知**：利用工作记忆中的用户目标和近期事件提升评分准确性

---

## 核心类

### `Evaluator`

**功能**：深度记忆价值评估器 — 记忆系统的前额叶皮层

**方法**：
- `evaluate(message, working_memory)` → 评估消息的记忆价值

---

## 核心方法

### `evaluate(message: str, working_memory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]`

**功能**：评估消息的记忆价值

**参数**：
- `message` (str)：要评估的消息文本
- `working_memory` (Optional[Dict[str, Any]])：可选的会话工作记忆，包含用户目标和近期焦点

**返回**：
```python
{
  "task_relevance": int,        # 0-10，任务相关性
  "emotional_intensity": int,   # 0-10，情绪强度
  "emotion_type": str,          # joy/sadness/anger/fear/surprise/neutral
  "novelty": int,               # 0-10，新颖性
  "encode_decision": bool,      # 是否编码
  "encode_priority": str,       # high/medium/low
  "reason": str                 # 一句话解释
}
```

**流程**：
```
1. 构建评估提示词（包含消息和工作记忆上下文）
2. 调用 LLM（call_llm_json）进行评估
3. 验证并规范化返回结果：
   a. 验证三维度评分（0-10）
   b. 验证情绪类型（6种有效值）
   c. 验证优先级（3种有效值）
   d. 重新应用编码规则（确保一致性）
4. 返回验证后的结果
```

**错误处理**：
- LLM 调用失败时返回默认值：
  ```python
  {
    "task_relevance": 5,
    "emotional_intensity": 0,
    "emotion_type": "neutral",
    "novelty": 5,
    "encode_decision": True,
    "encode_priority": "low",
    "reason": "evaluation error, defaulting to encode: <error>"
  }
  ```
- 采用 **fail-safe** 策略：失败时默认编码，避免漏掉重要信息

**调用链路**：
- `app.py` `_process_after_response()` → `Evaluator.evaluate()` → `call_llm_json()` → `_build_prompt()` → `_validate()`

---

## 评估维度

### 1. task_relevance（任务相关性）0-10

**定义**：消息与用户已知目标的相关程度

**评分锚点**：
- **0-2**：完全无关（如随机闲聊、天气小谈）
- **3-4**：切线相关（如提到用户工作领域的话题）
- **5-6**：中度相关（如活跃项目的进度更新）
- **7-8**：直接推进关键目标（如"我拿到了字节的面试"）
- **9-10**：关键人生决策或里程碑（如"我决定辞职"、"我拿到了offer"）

**上下文增强**：
- 如果工作记忆中有用户目标（`user_goals`），LLM 会参考这些目标进行评分
- 如果工作记忆中有近期事件（`recent_events`），LLM 会考虑消息是否与这些事件相关

---

### 2. emotional_intensity（情绪强度）0-10

**定义**：消息中情绪的强烈程度

**评分锚点**：
- **0-2**：中性，事实陈述
- **3-4**：轻微情绪（轻微沮丧、轻微开心）
- **5-6**：中等情绪（明显开心、明显压力）
- **7-8**：强烈情绪（非常兴奋、非常愤怒、哭泣）
- **9-10**：极端情绪（改变人生的喜悦、深度悲伤、恐慌）

**情绪类型**（`emotion_type`）：
- `joy`：喜悦
- `sadness`：悲伤
- `anger`：愤怒
- `fear`：恐惧
- `surprise`：惊讶
- `neutral`：中性

---

### 3. novelty（新颖性）0-10

**定义**：消息中信息的新颖程度

**评分锚点**：
- **0-2**：已知信息、重复事实、**或已存储在记忆中的信息**、**或临时调试/排查问题**
- **3-4**：已知话题的小细节
- **5-6**：有意义的新信息
- **7-8**：令人惊讶的新事实或意外发展
- **9-10**：完全意外、范式转变的信息

**关键规则**：
- 如果用户上下文显示信息已知（如"用户在美团工作"已在上下文中），评分应为 **0-2**
- 调试查询（如"为什么有两个服务"）应评分为 **0-2**，因为是临时性的，不值得长期记忆

---

## 编码决策规则

**按优先级应用以下规则**：

1. **高优先级编码**：
   - `task_relevance >= 7` → `encode_decision = true`, `encode_priority = "high"`
   - `emotional_intensity >= 7` → `encode_decision = true`, `encode_priority = "high"`

2. **中优先级编码**：
   - `novelty >= 8` → `encode_decision = true`, `encode_priority = "medium"`

3. **低优先级编码**：
   - `task_relevance >= 5` OR `novelty >= 5` → `encode_decision = true`, `encode_priority = "low"`

4. **不编码**：
   - 其他情况 → `encode_decision = false`, `encode_priority = "low"`

**注意**：这些规则在 `_validate()` 方法中重新应用，确保 LLM 返回的决策与规则一致。

---

## 内部辅助方法

### `_build_prompt(message: str, working_memory: Optional[Dict[str, Any]]) -> str`

**功能**：构建包含工作记忆上下文的评估提示词

**参数**：
- `message` (str)：要评估的消息
- `working_memory` (Optional[Dict[str, Any]])：工作记忆上下文

**返回**：
- 格式化的提示词字符串

**流程**：
```
1. 添加消息本身
2. 如果有工作记忆，添加上下文：
   a. 用户活跃目标（user_goals）
   b. 近期关键事件（recent_events，最多5条）
   c. 用户画像（user_profile）
3. 拼接所有部分并返回
```

**示例输出**：
```
Message to evaluate:
"""
我拿到了字节的面试
"""

Context for task_relevance scoring:
User's active goals:
- 跳槽到AI创业公司
- 减肥到85kg

Recent key events: 腾讯一面通过; 美团团队政治危机; 开始准备面试

User profile: {'name': '赵禹', 'age': 29, 'occupation': 'AI应用后端开发'}
```

**调用链路**：
- `evaluate()` → `_build_prompt()`

---

### `_validate(result: Dict[str, Any]) -> Dict[str, Any]`

**功能**：验证并规范化 LLM 评估结果

**参数**：
- `result` (Dict[str, Any])：LLM 返回的原始结果

**返回**：
- 验证并规范化后的结果

**流程**：
```
1. 验证三维度评分（0-10）：
   - 使用 clamp_int() 限制范围
   - 无效值默认为 5（task_relevance, novelty）或 0（emotional_intensity）
2. 验证情绪类型：
   - 必须是 6 种有效值之一
   - 无效值默认为 "neutral"
3. 验证优先级：
   - 必须是 "high"/"medium"/"low" 之一
   - 无效值默认为 "low"
4. 重新应用编码规则：
   - 确保 encode_decision 和 encode_priority 与评分一致
5. 返回验证后的结果
```

**关键逻辑**：
```python
# 重新应用编码规则
if task_relevance >= 7 or emotional_intensity >= 7 or novelty >= 8:
    encode_decision = True
    if task_relevance >= 7 or emotional_intensity >= 7:
        encode_priority = "high"
elif task_relevance >= 5 or novelty >= 5:
    encode_decision = True
    if encode_priority == "high":
        pass  # 保持 LLM 的高优先级判断
    else:
        encode_priority = "low"
```

**调用链路**：
- `evaluate()` → `_validate()`

---

## 系统提示词

### `_SYSTEM_PROMPT`

**功能**：定义 LLM 的评估角色和规则

**核心内容**：

#### 角色定义
你是 AI Agent 长期记忆系统的记忆价值评估器。你的任务是评估一条消息是否值得存储到长期记忆中。

#### 评估维度
在三个维度上评估消息（0-10 整数评分）。**使用完整的 0-10 范围 — 不要将评分聚集在 3-5 之间**。

#### 评分锚点
详细定义了三个维度的评分标准（见上文"评估维度"部分）。

#### 编码决策规则
详细定义了编码决策的优先级规则（见上文"编码决策规则"部分）。

#### 返回格式
```json
{
  "task_relevance": <0-10>,
  "emotional_intensity": <0-10>,
  "emotion_type": "joy|sadness|anger|fear|surprise|neutral",
  "novelty": <0-10>,
  "encode_decision": true|false,
  "encode_priority": "high|medium|low",
  "reason": "one-sentence explanation"
}
```

---

## 调用关系图

```
evaluator.py
└── Evaluator
    └── evaluate()
        ├── _build_prompt()
        ├── call_llm_json()
        └── _validate()
            └── clamp_int()
```

**被调用者**：
```
app.py
└── _process_after_response()
    └── Evaluator.evaluate()
```

---

## 重要注意事项

1. **上下文感知**：利用工作记忆中的用户目标和近期事件提升 `task_relevance` 评分准确性
2. **全范围评分**：强调使用完整的 0-10 范围，避免评分聚集在中间值
3. **规则一致性**：`_validate()` 重新应用编码规则，确保 LLM 返回的决策与规则一致
4. **fail-safe 策略**：LLM 调用失败时默认编码，避免漏掉重要信息
5. **情绪类型验证**：严格验证情绪类型，无效值默认为 `neutral`
6. **优先级验证**：严格验证优先级，无效值默认为 `low`
7. **新颖性去重**：如果信息已在上下文中，`novelty` 应评分为 0-2
8. **临时信息过滤**：调试/排查问题的临时查询应评分为低 `novelty`（0-2）
9. **用户画像注入**：将用户画像注入提示词，帮助 LLM 更好地理解上下文
10. **自动通过类别**：某些类别（`log_*`、`reconsolidation`、`prospective`、`forget`）在 `app.py` 中绕过评估器，直接编码

---

## 代码示例

### 评估一条消息
```python
evaluator = Evaluator()

message = "我拿到了字节的面试"
working_memory = {
    "user_goals": ["跳槽到AI创业公司", "减肥到85kg"],
    "raw": {
        "recent_events": [
            {"summary": "腾讯一面通过"},
            {"summary": "美团团队政治危机"},
        ],
        "user_profile": {
            "name": "赵禹",
            "age": 29,
            "occupation": "AI应用后端开发"
        }
    }
}

result = await evaluator.evaluate(message, working_memory)

# 预期结果：
# {
#   "task_relevance": 8,
#   "emotional_intensity": 6,
#   "emotion_type": "joy",
#   "novelty": 7,
#   "encode_decision": True,
#   "encode_priority": "high",
#   "reason": "直接推进跳槽目标，情绪积极"
# }
```

### 评估一条低价值消息
```python
message = "今天天气不错"
working_memory = None

result = await evaluator.evaluate(message, working_memory)

# 预期结果：
# {
#   "task_relevance": 1,
#   "emotional_intensity": 0,
#   "emotion_type": "neutral",
#   "novelty": 1,
#   "encode_decision": False,
#   "encode_priority": "low",
#   "reason": "无个人相关信息，纯天气闲聊"
# }
```

---

## 优化历史

- **初始版本**：基于三维度评分的记忆价值评估器
- **v2**：加强上下文感知，注入用户目标和近期事件
- **v3**：强调全范围评分，避免评分聚集
- **v4**：加强新颖性去重规则，过滤已知信息和临时调试查询
