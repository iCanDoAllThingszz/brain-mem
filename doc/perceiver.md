# perceiver.py - 感知器引擎

## 文件整体功能

`perceiver.py` 是 Brain Memory Service 的感知门户，对应人脑的**感觉皮层 + 丘脑**。它负责：

1. **消息分类**：将用户消息分类为 `noise`（噪音）、`command`（指令）、`informative`（信息型）
2. **消息重写**：将信息型消息重写为高密度、实体明确的记忆陈述
3. **类别识别**：识别消息的具体类别（认知、日志、重固化、前瞻记忆、遗忘）
4. **上下文消歧**：利用用户画像和工作记忆进行语义消歧

---

## 核心类

### `Perceiver`

**功能**：感知器 v2 — 分类并重写消息

**方法**：
- `classify(message, working_memory)` → 分类并重写消息

---

## 核心方法

### `classify(message: str, working_memory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]`

**功能**：分类并可选地重写消息

**参数**：
- `message` (str)：用户消息
- `working_memory` (Optional[Dict[str, Any]])：工作记忆上下文（可选）

**返回**：
```python
{
  "type": "noise" | "command" | "informative",
  "category": "cognition" | "log_*" | "reconsolidation" | "prospective" | "forget",
  "target_entity": str | None,
  "correction_type": "correct" | "supplement" | "reframe" | None,
  "trigger_type": "time" | "event" | "condition" | None,
  "trigger_value": str | None,
  "action": str | None,
  "reason": str,
  "rewrite": str | None
}
```

**流程**：
```
1. 构建提示词（包含消息和工作记忆上下文）
2. 调用 LLM（call_llm_json）进行分类和重写
3. 验证返回结果：
   a. 验证 type（noise/command/informative）
   b. 验证 category（cognition/log_*/reconsolidation/prospective/forget）
   c. 验证 target_entity（根据 category）
   d. 验证 correction_type（reconsolidation 必需）
   e. 验证 trigger_type/trigger_value/action（prospective 必需）
   f. 验证 rewrite（仅 informative 类型有效）
4. 返回验证后的结果
```

**关键逻辑**：

#### 1. 消息类型分类
- **noise（噪音）**：零个人信息内容
  - 纯社交填充词："嗯嗯"、"好的"、"哈哈"、"OK"、"收到"
  - 通用常识："地球是圆的"、"天是蓝的"、"水是H2O"
  - 无个人语境的天气/时间评论

- **command（指令）**：纯指令，不包含个人信息
  - 示例："翻译这段话"、"查一下天气"、"检查一下日志"、"为什么会有两个服务"

- **informative（信息型）**：包含值得记住的用户信息
  - 显性信息：事实、决策、计划
  - 隐性信息：问题透露的兴趣、语气透露的情绪、请求透露的意图

#### 2. 消息类别识别
- **cognition（认知）**：直接影响用户画像、目标、决策、关系或里程碑的信息
  - **关键**：任何引入新人物、描述关系或解释组织动态的消息必须是 `cognition`
  - 示例：
    - "我决定学Rust" → cognition（决策）
    - "我打算开始减肥" → cognition（计划）
    - "腾讯面试过了" → cognition（里程碑）
    - "凡哥是我的直属leader" → cognition（关系）
    - "梦阳今天提离职了" → cognition（人事变动）
    - "少栋是我的虚线，鹏程是我同事" → cognition（组织架构）

- **log_diet（饮食日志）**：仅实际饮食/食物消费记录
  - 示例："吃了苹果"、"午餐牛肉面600大卡"
  - 默认 `target_entity`："减肥计划"

- **log_exercise（运动日志）**：仅实际运动/锻炼记录
  - 示例："跑了5公里"、"做了30个俯卧撑"
  - 默认 `target_entity`："减肥计划"

- **log_interview（面试日志）**：仅面试会话细节/反馈
  - 示例："腾讯二面聊了分布式系统"
  - 默认 `target_entity`："跳槽计划"

- **log_trading（交易日志）**：仅交易记录或市场观察
  - 示例："买了0.1个BTC"
  - 默认 `target_entity`："量化交易"

- **log_learning（学习日志）**：仅实际学习笔记或学习记录
  - 示例："今天学了Rust的所有权机制"
  - 注意：学习决策是 `cognition`，不是 `log_learning`

- **log_general（通用日志）**：不符合上述类别的其他日志型信息

- **reconsolidation（记忆重固化）**：用户在纠正、补充或重新诠释之前的记忆
  - 总是设置 `target_entity`（被纠正的实体）
  - 总是设置 `correction_type`：
    - `correct`：事实纠正（如"不对，我当时说的是感觉很好"）
    - `supplement`：添加新信息（如"腾讯一面过了，下周二面"）
    - `reframe`：情感重新诠释（如"美团那段时间其实很痛苦"）

- **prospective（前瞻记忆）**：用户在设置未来的提醒或意图
  - 总是设置 `trigger_type`：
    - `time`：基于时间的触发（如"明天提醒我交报告"）
    - `event`：基于事件的触发（如"下次聊到面试时问问字节结果"）
    - `condition`：基于条件的触发（如"如果BTC跌破6万提醒我"）
  - 总是设置 `trigger_value`：具体触发条件（ISO格式时间、事件关键词或条件表达式）
  - 总是设置 `action`：触发时要做什么
  - 示例：
    - "明天早上9点提醒我交报告" → `trigger_type="time"`, `trigger_value="2026-03-15T09:00:00+08:00"`, `action="提醒交报告"`
    - "下次聊到减肥时提醒我记录饮食" → `trigger_type="event"`, `trigger_value="减肥"`, `action="提醒记录饮食"`
    - "如果BTC跌破6万提醒我" → `trigger_type="condition"`, `trigger_value="BTC<60000"`, `action="提醒BTC跌破6万"`

- **forget（遗忘）**：用户想要遗忘或抑制某个记忆
  - 总是设置 `target_entity`：要遗忘的实体/记忆
  - 示例：
    - "忘掉张三这个人" → `category="forget"`, `target_entity="张三"`
    - "不要再提那次失败的面试" → `category="forget"`, `target_entity="那次失败的面试"`

#### 3. 消息重写规则
对于 `informative` 类型的消息，重写为高密度记忆陈述，要求：

1. **明确用户（主语）**：使用上下文中的真实姓名
2. **记录陈述的事实**：不要将单次事件泛化为习惯或偏好
3. **关联已知上下文**：目标、近期事件、职业计划
4. **去除常识噪音**：只保留个人相关部分
5. **明确实体关系**
6. **保留原始意图**：不要过度推断或改变语义
7. **禁止过度推断**：单次行为不代表习惯或偏好

**重写示例**：

| 原文 | 上下文 | 重写 |
|------|--------|------|
| "最近ai agent有啥新动向" | 用户是赵禹，计划跳槽AI创业公司 | "赵禹询问AI Agent最新动态，表明他持续关注AI Agent领域，与跳槽AI创业公司的职业规划相关" |
| "帮我搜一下上海AI公司" | 用户计划搬到上海 | "赵禹正在调研上海AI公司，这是他跳槽计划的具体行动步骤" |
| "今天好累" | 用户最近忙于面试和工作 | "赵禹表达疲惫感，可能与近期面试和工作双线压力有关" |
| "地球是圆的，对了我打算学Rust" | - | "赵禹计划学习Rust语言以拓展技术栈" |
| "好的 明天开始记录饮食" | 用户有减肥计划，已停滞4天 | "赵禹承诺明天重新开始记录饮食，减肥计划即将恢复" |
| "早上我吃了一个苹果" | - | "赵禹早上吃了一个苹果" ❌ 错误："赵禹有早餐吃水果的习惯" |
| "我今天中午吃了一碗牛肉面 大概600大卡" | - | "赵禹今日午餐吃了一碗牛肉面，约600大卡" ❌ 错误："赵禹喜欢吃牛肉面" |
| "怎么会有两个服务 不是就一个服务吗" | 用户在调试记忆系统项目 | "赵禹对系统中存在两个服务表示疑惑，认为应该只有一个服务" |

**调用链路**：
- `app.py` `_process_after_response()` → `Perceiver.classify()` → `call_llm_json()` → `_build_prompt()`

---

## 内部辅助方法

### `_build_prompt(message: str, working_memory: Optional[Dict[str, Any]]) -> str`

**功能**：构建包含丰富上下文的用户提示词

**参数**：
- `message` (str)：用户消息
- `working_memory` (Optional[Dict[str, Any]])：工作记忆上下文

**返回**：
- 格式化的提示词字符串

**流程**：
```
1. 添加消息本身
2. 如果有工作记忆，添加上下文：
   a. 用户画像（user_profile）
   b. 活跃目标（user_goals）
   c. 近期事件（recent_events，最多5条）
   d. 当前上下文（context，截断到400字符）
   e. 情绪基线（emotional_baseline）
3. 拼接所有部分并返回
```

**示例输出**：
```
Message:
"""
最近ai agent有啥新动向
"""

User context (use for rewriting):
User profile: {'name': '赵禹', 'age': 29, 'occupation': 'AI应用后端开发'}
Active goals: 跳槽到AI创业公司, 减肥到85kg
Recent events: 腾讯一面通过; 美团团队政治危机; 开始准备面试
Current context: 赵禹正在准备跳槽面试，关注AI领域最新动态...
Emotional state: stressed
```

**调用链路**：
- `classify()` → `_build_prompt()`

---

## 系统提示词

### `_SYSTEM_PROMPT`

**功能**：定义 LLM 的角色和任务规则

**核心内容**：

#### 任务1：分类
将消息分类为 `noise`、`command`、`informative` 三种类型之一。

**关键规则**：
- 问题透露兴趣："最近AI agent有啥新动向" → 用户对AI agent感兴趣
- 指令透露意图："帮我搜上海AI公司" → 用户在调研AI公司
- 情绪透露状态："今天好累" → 用户疲惫
- 混合消息：如果包含任何个人信息，分类为 `informative`
- 不确定时 → `informative`（召回优先原则）

#### 任务2：重写（仅当 type = "informative" 时）
将原始消息重写为高密度记忆陈述。

**重写要求**：
1. 明确用户（主语）— 使用上下文中的真实姓名
2. 记录陈述的事实 — 不要将单次事件泛化为习惯或偏好
3. 关联已知上下文（目标、近期事件、职业计划）
4. 去除常识噪音，只保留个人相关部分
5. 明确实体关系
6. **保留原始意图** — 不要过度推断或改变语义
7. **禁止过度推断** — 单次行为不代表习惯或偏好

**返回格式**：
```json
{
  "type": "noise" | "command" | "informative",
  "category": "cognition" | "log_diet" | "log_exercise" | "log_interview" | "log_trading" | "log_learning" | "log_general" | "reconsolidation" | "prospective" | "forget",
  "target_entity": "需要更新的实体名称" | null,
  "correction_type": "correct" | "supplement" | "reframe" | null,
  "trigger_type": "time" | "event" | "condition" | null,
  "trigger_value": "具体触发条件" | null,
  "action": "要做的事" | null,
  "reason": "一句话分类解释",
  "rewrite": "重写后的高密度记忆陈述" | null
}
```

---

## 调用关系图

```
perceiver.py
└── Perceiver
    └── classify()
        ├── _build_prompt()
        └── call_llm_json()
```

**被调用者**：
```
app.py
└── _process_after_response()
    └── Perceiver.classify()
```

---

## 重要注意事项

1. **上下文消歧**：利用工作记忆中的用户画像、目标、近期事件进行语义消歧
2. **召回优先**：不确定时优先分类为 `informative`，避免漏掉重要信息
3. **重写质量**：重写必须高密度、实体明确、关联上下文，避免过度推断
4. **类别验证**：严格验证 `category` 和相关字段（`target_entity`、`correction_type`、`trigger_type` 等）
5. **错误容错**：LLM 调用失败时返回默认值（`informative` + `cognition`），确保不阻塞流程
6. **人际关系识别**：任何涉及新人物、关系、组织架构的消息必须是 `cognition`，不是 `log`
7. **前瞻记忆时间解析**：相对时间（"明天"、"下周"）需解析为绝对 ISO datetime（北京时间 UTC+8）
8. **遗忘机制**：支持用户主动遗忘不想要的记忆，通过 `forget` 类别实现
9. **重固化支持**：支持用户纠正、补充或重新诠释之前的记忆，通过 `reconsolidation` 类别实现
10. **日志分类细化**：区分饮食、运动、面试、交易、学习等不同类型的日志，便于后续处理

---

## 优化历史

- **2026-03-17**：加强人际关系/组织架构识别规则，提示词中文化
- **v2**：不仅分类，还将信息型消息重写为高密度、实体明确的记忆输入
