<p align="center">
  <h1 align="center">🧠 Brain-Mem</h1>
  <p align="center"><strong>基于认知科学的 AI 智能体记忆系统</strong></p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Neo4j-5.x-008CC1.svg" alt="Neo4j">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688.svg" alt="FastAPI">
</p>

<p align="center">
  <a href="README.md">English</a> | <strong>中文</strong>
</p>

---

## 🎯 概述

Brain-Mem 是一个生产级记忆系统，忠实模拟**人脑**处理、存储、巩固和检索记忆的方式。与简单的向量数据库或键值存储不同，Brain-Mem 实现了认知科学机制，包括选择性编码、睡眠巩固、间隔重复、情绪共鸣、前瞻性记忆和自然遗忘。

作为 **OpenClaw 插件**构建，Brain-Mem 通过事件驱动的钩子与 AI 智能体无缝集成，无需修改智能体代码即可提供上下文感知的记忆。

### 核心亮点

- 🧠 **认知架构** — 将大脑区域（海马体、前额叶皮层、杏仁核）映射到系统组件
- 🏗️ **分层存储** — 知识图谱存储认知，文件系统存储详细日志，缓冲区用于暂存
- 🔄 **睡眠巩固** — 批处理强化重要记忆并修剪噪声
- 🎯 **多路径检索** — 5 种检索策略，结合情绪共鸣和失败补偿
- ⏰ **前瞻性记忆** — 基于时间和事件的未来提醒
- 📊 **间隔重复** — 基于艾宾浩斯遗忘曲线的自动复习调度
- 🔗 **实体解析** — LLM 驱动的名称映射和去重
- 🔌 **OpenClaw 插件** — 零代码集成

---

## 🤔 为什么选择 Brain-Mem？

大多数 AI 记忆系统将记忆视为扁平数据库：存储一切，通过相似度检索。人脑的工作方式根本不同：

| 人脑机制 | Brain-Mem 实现 |
|---------|---------------|
| **选择性编码** — 并非所有信息都被存储 | Perceiver 过滤噪声，Evaluator 按重要性门控 |
| **睡眠巩固** — 休息期间记忆得到强化 | Consolidator 批处理缓冲区 → 图谱，包含 12 步流水线 |
| **多路径检索** — 通过名称、情绪、上下文回忆 | 5 种检索策略 + 情绪共鸣加权 |
| **自然遗忘** — 防止信息过载 | 衰减机制，重要性加权半衰期 |
| **前瞻性记忆** — "当 X 发生时提醒我" | 基于时间和事件的触发器存储在图谱中 |
| **实体解析** — "小张" = "张三" = "我同事" | LLM 驱动的名称映射，层次化标签搜索 |
| **跨会话连续性** — 从不从零开始 | 会话摘要桥接对话 |

### 与其他系统对比

| 功能 | Brain-Mem | mem0 | Letta | 向量数据库 |
|------|:---------:|:----:|:-----:|:----------:|
| 认知架构 | ✅ | ❌ | ❌ | ❌ |
| 知识图谱 | ✅ Neo4j | ❌ | ❌ | ❌ |
| 分层存储 | ✅ 三层 | ❌ | ❌ | ❌ |
| 实体解析 | ✅ LLM | ❌ | ❌ | ❌ |
| 多路径检索 | ✅ 5 路径 | ❌ 仅向量 | ❌ | ❌ 仅向量 |
| 睡眠巩固 | ✅ 12 步 | ❌ | ❌ | ❌ |
| 间隔重复 | ✅ | ❌ | ❌ | ❌ |
| 情绪共鸣 | ✅ | ❌ | ❌ | ❌ |
| 前瞻性记忆 | ✅ | ❌ | ❌ | ❌ |
| 自然遗忘 | ✅ 衰减 | ❌ | ❌ | ❌ |
| 会话摘要 | ✅ | ❌ | ✅ | ❌ |
| 多租户 | ✅ | ✅ | ❌ | 视情况 |
| OpenClaw 插件 | ✅ | ❌ | ❌ | ❌ |

---

## 🚀 快速开始

### 前置要求

- Docker & Docker Compose
- OpenAI 兼容的 LLM API（OpenAI、Azure、MiniMax 或通过 vLLM/Ollama 的本地模型）
- 最低 2GB RAM，推荐 4GB

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/brain-mem.git
cd brain-mem

# 复制并配置
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入你的 LLM API 凭证

# 启动服务
docker compose up -d

# 验证健康状态
curl http://localhost:8100/health
```

**服务：**
- Brain-Mem API: `http://localhost:8100`
- Neo4j 浏览器: `http://localhost:7474`（用户名：`neo4j`，密码：来自 `NEO4J_PASSWORD` 环境变量）

### 配置

编辑 `config.yaml`：

```yaml
neo4j:
  uri: "bolt://neo4j:7687"  # 本地部署使用 "bolt://localhost:7687"
  user: "neo4j"
  password: "your_password"

llm:
  base_url: "https://api.openai.com/v1"
  api_key: "sk-..."
  model: "gpt-4o"

embedding:
  base_url: "https://api.openai.com/v1"
  api_key: "sk-..."
  model: "text-embedding-3-small"
```

### 设置巩固定时任务

记忆巩固应每天运行（模拟睡眠）：

```bash
# 添加到 crontab（每天凌晨 1:30 运行）
30 1 * * * curl -X POST http://localhost:8100/hooks/consolidate \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"default","user_id":"your_user"}' \
  >> /var/log/brain-mem-consolidation.log 2>&1
```


---

## 🏗️ 架构

### 系统概览

```
┌─────────────────────────────────────────────────────────────┐
│                        输入消息                              │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────▼────────────────┐
         │  👁️ Perceiver                  │  过滤噪声，分类
         │  (感觉皮层 + 丘脑)             │  路由：认知 vs 日志
         └───────────────┬────────────────┘
                         │
         ┌───────────────▼────────────────┐
         │  🧪 Evaluator                  │  评分重要性、新颖性
         │  (前额叶 + 杏仁核)             │  门控长期存储
         └───────────────┬────────────────┘
                         │
         ┌───────────────▼────────────────┐
         │  🏗️ Encoder                    │  实体解析
         │  (海马体)                      │  名称映射、关系
         └─────┬──────────────────┬───────┘
               │                  │
    ┌──────────▼─────┐   ┌───────▼────────┐
    │ 📦 Buffer       │   │ 📝 文件日志     │
    │ (SQLite)        │   │ (Markdown)     │
    └──────────┬──────┘   └────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │  💤 Consolidator                    │  睡眠巩固
    │  (缓冲区 → 图谱)                    │  间隔重复
    └──────────┬──────────────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │  📊 知识图谱 (Neo4j)                │  长期记忆
    │  + 向量索引                         │  实体 + 关系
    └─────────────────────────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │  🔍 Retriever                       │  多路径回忆
    │  (5 种策略 + 情绪)                  │  上下文合成
    └─────────────────────────────────────┘
```

### 脑科学启发的组件映射

| 大脑区域 | 组件 | 功能 | 实现 |
|---------|------|------|------|
| **感觉皮层 + 丘脑** | Perceiver | 过滤噪声，分类信息类型 | 基于 LLM 的分类：`noise`、`command`、`informative` |
| **前额叶皮层 + 杏仁核** | Evaluator | 评分重要性、新颖性、情绪显著性 | 多维度评分：任务相关性、情绪强度、新颖性 |
| **海马体** | Encoder | 实体生命周期、名称解析、关系映射 | 层次化标签搜索 + LLM 解析 + 名称映射 |
| **睡眠巩固** | Consolidator | 缓冲区→图谱转移、冲突解决、间隔重复 | 12 步流水线，包含模式发现和图谱清理 |
| **长期记忆** | Neo4j 图谱 | 持久化知识存储，向量搜索 | 图数据库 + 原生向量索引 |
| **工作记忆** | Working Memory | 每会话上下文缓存 | 内存缓存，会话生命周期 |
| **前瞻性记忆** | Prospective Checker | 面向未来的提醒 | 基于时间/事件的触发器，支持重复次数 |

---

## 🎨 核心功能

### 1. 分层存储架构

大脑不会用存储购物清单的方式来存储人生决策。Brain-Mem 使用三层存储模型：

**📊 知识图谱 (Neo4j)** — 高层次认知
- 目标、决策、关系、里程碑、洞察
- 重要性 ≥ 5.0 的实体
- 向量嵌入用于语义搜索
- 示例："职业目标：Q3 前转型到 AI 研究"

**📝 文件系统 (Markdown)** — 详细日志
- 饮食记录、运动日志、面试笔记
- 交易记录、学习日志、会议纪要
- 按类别和日期组织
- 示例：`memory/logs/diet/2026-03-22.md`

**📦 缓冲区 (SQLite)** — 短期暂存
- 等待巩固的编码记忆单元
- 跨会话连续性的会话摘要
- 类型过滤读取（记忆 vs 摘要）

**示例：**
```
用户："我早餐吃了一个苹果"

❌ 没有分层存储：
   → 创建实体：苹果、用户、早餐水果习惯
   → 图谱被琐碎的食物项污染

✅ 有分层存储：
   → 追加到 memory/logs/diet/2026-03-22.md
   → 更新图谱：DietPlan.last_diet_log = "2026-03-22"
   → 图谱保持清洁，细节得以保留
```

### 2. 实体解析与名称映射

编码器不会盲目创建节点。它遵循严格的生命周期：

1. **层次化标签分配** — 使用两级标签树对实体分类
2. **同类型检索** — 搜索具有匹配标签的现有节点
3. **LLM 解析** — 决定：`create`、`merge` 或 `update`
4. **名称映射** — 构建 `原始名称 → 最终名称` 映射
5. **关系对齐** — 将映射应用于所有关系
6. **嵌入生成** — 自动生成向量嵌入

**示例：**
```
用户："我同事在做 AI 项目"
→ "我同事" 解析为现有节点 "张三"
→ 关系修正：from_name="张三"（而非 "我同事"）
→ 无孤立引用
```


### 3. 多路径检索

人类记忆检索不是单一机制。Brain-Mem 实现了 5 种策略：

| 路径 | 策略 | 使用场景 | 示例 |
|------|------|---------|------|
| **A** | 精确名称匹配 | 直接实体查找 | "张三" → 找到节点 |
| **B** | 别名匹配 | 昵称/引用 | "那个 AI 项目" → 匹配项目别名 |
| **C** | 模糊关键词 | 部分匹配 | "项目" → 找到 "AI 项目" |
| **D** | 休眠重激活 | 重新浮现旧记忆 | 检索强度 < 2.0 的节点 |
| **E** | 向量语义 | 基于含义 | "机器学习工作" → 找到 "AI 研究" |

**附加机制：**
- **情绪共鸣** — 当前情绪动态调整评分权重
- **失败补偿** — 如果结果不足，自动扩展到 3 跳图遍历
- **综合评分** — 相关性 (40-50%) + 重要性 (15%) + 时效性 (15%) + 访问频率 (10%) + 情绪 (10-20%)

### 4. 睡眠巩固

模拟大脑睡眠阶段的记忆巩固，包含 12 步流水线：

1. **缓冲区读取** — 获取未归档的记忆单元
2. **实体更新插入** — 在图谱中创建/合并/更新节点
3. **关系创建** — 构建知识图谱连接
4. **嵌入生成** — 为新节点自动生成向量
5. **模式发现** — LLM 发现跨事件模式
6. **冲突解决** — 解决矛盾记忆
7. **孤立节点修复** — 连接孤立节点
8. **创造性重组** — 发现非显而易见的洞察
9. **图谱清理** — 合并重复项，抑制噪声
10. **隐式关系** — 推断缺失连接
11. **记忆衰减** — 应用遗忘曲线
12. **间隔重复** — 为重要记忆安排复习

**触发器：** 每日定时任务（推荐：凌晨 1:30）

**为什么巩固很重要：**
- **模式发现**："用户本周提到 3 次'截止日期压力' → 创建模式节点"
- **冲突解决**："用户昨天说'我爱咖啡'，今天说'我戒咖啡了' → 解决矛盾"
- **图谱清理**："合并重复节点：'AI 项目' 和 'AI项目' → 单一节点"

### 5. 间隔重复

使用艾宾浩斯遗忘曲线防止重要记忆淡化：

- **复习间隔：** 1 → 3 → 7 → 21 天，然后翻倍
- **自动强化：** Consolidator 直接提升 `retrieval_strength`
- **抗衰减：** 重要节点（重要性 ≥ 6.0）定期复习
- **无需用户操作：** 系统自动维护记忆强度

**机制：**
```python
# 衰减公式（在巩固期间应用）
days_since_access = (now - last_access_time).days
decay_rate = 0.1 if importance >= 6.0 else 0.2
new_strength = old_strength * exp(-decay_rate * days_since_access)

# 间隔重复调度
if importance >= 6.0 and strength < threshold:
    next_review = last_review + interval
    intervals = [1, 3, 7, 21, 42, 84, ...]  # 天数
```

### 6. 前瞻性记忆

面向未来的提醒，包含两种触发类型：

**基于时间：**
```
"明天下午 3 点提醒我给客户打电话"
→ 存储为 trigger_time="2026-03-24T15:00:00Z"
→ 在指定时间触发（会话开始时检查）
```

**基于事件：**
```
"当我提到项目时，提醒我更新时间线"
→ 当查询匹配触发关键词时触发
→ 支持重复次数（1=一次性，0=无限，N=有限）
```

### 7. 情绪共鸣

情绪影响记忆检索：

- **情绪标记** — 节点携带 `emotional_tag`（类型 + 强度）
- **动态加权** — 当前情绪提升匹配记忆
- **鼓励规则** — 负面情绪提升正面记忆
- **强度缩放** — 强度越高 = 影响越强

**示例：**
```
用户情绪：焦虑（强度：7）
查询："我该怎么办？"

检索评分：
- 节点 A（平静，重要性：8）→ 通过鼓励规则提升
- 节点 B（焦虑，重要性：6）→ 通过情绪匹配提升
- 节点 C（中性，重要性：9）→ 标准评分
```


---

## 🔌 OpenClaw 插件集成

Brain-Mem 通过事件驱动的钩子与 OpenClaw 无缝集成。无需修改智能体代码。

### 钩子生命周期

**1. brain-memory-recall** (`message:preprocessed`)
- **触发时机：** 智能体处理用户消息之前
- **操作：** 
  - 调用 `/hooks/session-start`（如果是新会话）
  - 调用 `/hooks/before-query`（检索记忆）
- **注入：** 将 `<working-memory>` 和 `<retrieved-memories>` XML 块注入提示词
- **过滤：** 跳过定时任务、子智能体、心跳

**2. brain-memory-capture** (`message:preprocessed`)
- **触发时机：** 用户发送消息时
- **操作：** 将消息存储在临时映射中，供后续编码使用
- **TTL：** 2 分钟

**3. brain-memory-encode** (`message:sent`)
- **触发时机：** 智能体成功响应后
- **操作：** 使用用户 + 助手消息调用 `/hooks/after-response`
- **流水线：** Perceiver → Evaluator → Encoder（后台处理）

**4. brain-memory-session** (`command:new`)
- **触发时机：** 用户开始新对话时
- **操作：** 调用 `/hooks/session-end` 生成摘要
- **清理：** 销毁工作记忆缓存

### 安装

```bash
# 1. 在 OpenClaw 中安装插件
cd openclaw-plugin
npm install

# 2. 配置环境变量
export BRAIN_SERVER_URL="http://localhost:8100"
export BRAIN_TENANT_ID="default"
export BRAIN_USER_ID="your_user_id"

# 3. 在 OpenClaw 设置中注册插件
# 添加到 openclaw.config.json:
{
  "plugins": [
    {
      "name": "brain-memory",
      "path": "./openclaw-plugin"
    }
  ]
}
```

### 钩子配置

插件自动向 OpenClaw 注册钩子。`openclaw.plugin.json` 中的配置：

```json
{
  "name": "brain-memory",
  "version": "1.0.0",
  "hooks": [
    {
      "name": "brain-memory-recall",
      "event": "message:preprocessed",
      "priority": 10
    },
    {
      "name": "brain-memory-capture",
      "event": "message:preprocessed",
      "priority": 5
    },
    {
      "name": "brain-memory-encode",
      "event": "message:sent",
      "priority": 5
    },
    {
      "name": "brain-memory-session",
      "event": "command:new",
      "priority": 5
    }
  ]
}
```

### 记忆上下文注入

当用户发送消息时，插件注入记忆上下文：

```xml
<working-memory>
用户档案：软件工程师，对 AI 感兴趣
活跃目标：学习强化学习，构建聊天机器人
最近上下文：昨天讨论了 Transformer 架构
情绪基线：有动力，对截止日期略感压力
</working-memory>

<retrieved-memories>
1. [目标] Q2 结束前学习强化学习（重要性：8.5）
2. [项目] 使用 GPT-4 API 构建聊天机器人（重要性：7.0）
3. [知识] Transformer 架构使用自注意力（重要性：6.5）
</retrieved-memories>
```


---

## 📚 API 参考

### 核心端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查和版本 |
| `/logs?n=50` | GET | 最近活动日志 |
| `/hooks/session-start` | POST | 初始化会话，加载工作记忆 |
| `/hooks/before-query` | POST | 为查询检索记忆 |
| `/hooks/after-response` | POST | 编码新记忆 |
| `/hooks/session-end` | POST | 生成会话摘要 |
| `/hooks/consolidate` | POST | 触发巩固（定时任务） |
| `/hooks/check-prospective` | POST | 检查基于时间的提醒 |
| `/hooks/backfill-embeddings` | POST | 生成缺失的嵌入 |

### 状态检查端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/hooks/status/session-start` | GET | 检查 session-start 钩子日志 |
| `/hooks/status/before-query` | GET | 检查 before-query 钩子日志 |
| `/hooks/status/after-response` | GET | 检查 after-response 钩子日志 |
| `/hooks/status/session-end` | GET | 检查 session-end 钩子日志 |

### 示例：完整会话生命周期

```bash
# 1. 开始会话
curl -X POST http://localhost:8100/hooks/session-start \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "user_profile": {"name": "Alice", "role": "engineer"}
  }'

# 2. 带记忆上下文的查询
curl -X POST http://localhost:8100/hooks/before-query \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "query": "我的职业目标是什么？"
  }'

# 3. 对话后编码记忆
curl -X POST http://localhost:8100/hooks/after-response \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "user_message": "我决定转向 AI 研究",
    "assistant_response": "很好的选择！我会帮你准备。"
  }'

# 4. 结束会话
curl -X POST http://localhost:8100/hooks/session-end \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001"
  }'

# 5. 触发巩固（每日定时任务）
curl -X POST http://localhost:8100/hooks/consolidate \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice"
  }'
```


---

## 📁 项目结构

```
brain-mem/
├── server/
│   ├── app.py                      # FastAPI 应用和端点
│   ├── activity_log.py             # 活动日志
│   ├── engine/
│   │   ├── perceiver.py            # 👁️ 过滤与分类
│   │   ├── evaluator.py            # 🧪 评估重要性
│   │   ├── encoder.py              # 🏗️ 实体生命周期
│   │   ├── retriever.py            # 🔍 多路径检索
│   │   ├── consolidator.py         # 💤 睡眠巩固
│   │   ├── working_memory.py       # 🎯 会话上下文
│   │   ├── prospective_checker.py  # ⏰ 未来提醒
│   │   ├── profile_updater.py      # 👤 用户档案
│   │   ├── log_writer.py           # 📝 文件日志
│   │   ├── embedding_client.py     # 🔢 嵌入
│   │   └── llm_client.py           # 🤖 LLM 客户端
│   ├── storage/
│   │   ├── graph.py                # Neo4j 操作
│   │   ├── buffer.py               # SQLite 缓冲区
│   │   ├── tag_dict.py             # 标签层次
│   │   └── user_profile.py         # 档案存储
│   └── models/
│       ├── node.py                 # 节点模型
│       └── relation.py             # 关系模型
├── openclaw-plugin/
│   ├── index.ts                    # OpenClaw 集成
│   └── openclaw.plugin.json        # 插件元数据
├── config.yaml.example             # 配置模板
├── docker-compose.yml              # Docker 部署
├── Dockerfile                      # 容器构建
├── requirements.txt                # 依赖项
└── README.md                       # 文档
```

---

## 🛠️ 技术栈

- **运行时：** Python 3.11+ / FastAPI / Uvicorn
- **图数据库：** Neo4j 5.x（原生向量索引）
- **缓冲区：** SQLite（零配置，类型过滤）
- **LLM：** OpenAI 兼容 API（OpenAI、Azure、MiniMax、vLLM、Ollama）
- **嵌入：** text-embedding-3-small（1536 维）
- **插件：** TypeScript（OpenClaw）

---

## 🚀 开发

### 本地设置

```bash
# 克隆仓库
git clone https://github.com/yourusername/brain-mem.git
cd brain-mem

# 安装依赖
pip install -r requirements.txt

# 启动 Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:5

# 配置
cp config.yaml.example config.yaml
# 编辑 config.yaml

# 运行服务器
python -m uvicorn server.app:app --reload --port 8100
```

### 环境变量

```bash
# 使用环境变量覆盖 config.yaml
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_PASSWORD="your_password"
export LLM_API_KEY="sk-..."
export EMBEDDING_API_KEY="sk-..."
```

### Docker 部署

```bash
# 构建并启动
docker compose up -d

# 查看日志
docker compose logs -f brain-mem

# 停止服务
docker compose down
```


---

## 🔬 认知科学背景

Brain-Mem 基于已确立的认知科学和神经科学研究：

### 选择性编码（Craik & Lockhart, 1972）
并非所有信息都接受相同的处理深度。Brain-Mem 的 Perceiver 和 Evaluator 实现了加工水平理论，过滤噪声并按重要性门控存储。

### 睡眠巩固（Stickgold & Walker, 2005）
睡眠期间的记忆巩固强化重要记忆并修剪无关记忆。Brain-Mem 的 Consolidator 通过批处理、模式发现和图谱清理来模拟这一过程。

### 多存储记忆模型（Atkinson & Shiffrin, 1968）
信息流经感觉 → 短期 → 长期记忆。Brain-Mem 通过缓冲区（短期）→ 图谱（长期）架构实现这一点。

### 扩散激活（Collins & Loftus, 1975）
记忆检索激活相关概念。Brain-Mem 的多路径检索和 3 跳图遍历实现了扩散激活。

### 遗忘曲线（Ebbinghaus, 1885）
记忆强度随时间呈指数衰减。Brain-Mem 应用具有重要性加权半衰期的衰减机制。

### 间隔重复（Piotr Woźniak, 1985）
以递增间隔复习信息可防止遗忘。Brain-Mem 根据重要性和访问模式自动安排复习。

### 前瞻性记忆（Einstein & McDaniel, 1990）
面向未来的意图记忆。Brain-Mem 实现基于时间和事件的触发器。

### 情绪记忆（McGaugh, 2004）
情绪增强记忆编码和检索。Brain-Mem 的情绪共鸣机制根据情绪状态加权检索。

---

## 🔍 故障排除

**Neo4j 连接失败：**
```bash
# 检查 Neo4j 是否运行
docker ps | grep neo4j

# 验证 config.yaml 中的凭证
# 检查 Neo4j 日志
docker logs neo4j
```

**嵌入生成缓慢：**
```bash
# 检查嵌入 API 端点
curl -X POST https://api.openai.com/v1/embeddings \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"input":"test","model":"text-embedding-3-small"}'

# 考虑使用本地嵌入模型（例如 sentence-transformers）
```

**记忆未巩固：**
```bash
# 检查巩固日志
curl http://localhost:8100/logs?n=100 | grep consolidation

# 手动触发
curl -X POST http://localhost:8100/hooks/consolidate \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"default","user_id":"your_user"}'

# 检查缓冲区是否有数据
sqlite3 memory/buffer.db "SELECT COUNT(*) FROM memory_units WHERE archived=0"
```

**OpenClaw 插件不工作：**
```bash
# 检查环境变量
echo $BRAIN_SERVER_URL
echo $BRAIN_TENANT_ID
echo $BRAIN_USER_ID

# 检查 Brain-Mem 服务器是否可访问
curl http://localhost:8100/health

# 检查 OpenClaw 日志以查看钩子执行情况
```

**内存使用率高：**
```bash
# 检查 docker-compose.yml 中的 Neo4j 内存设置
# 调整 NEO4J_server_memory_heap_max__size

# 检查缓冲区大小
sqlite3 memory/buffer.db "SELECT COUNT(*) FROM memory_units"

# 运行巩固以将缓冲区 → 图谱
```


---

## 🤝 贡献

欢迎贡献！请遵循以下指南：

1. Fork 仓库
2. 创建功能分支（`git checkout -b feature/amazing-feature`）
3. 提交更改（`git commit -m 'Add amazing feature'`）
4. 推送到分支（`git push origin feature/amazing-feature`）
5. 打开 Pull Request

---

## 📄 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

## 📖 引用

如果您在研究中使用 Brain-Mem，请引用：

```bibtex
@software{brain_mem_2026,
  title = {Brain-Mem: A Cognitive Science-Inspired Memory System for AI Agents},
  year = {2026},
  url = {https://github.com/yourusername/brain-mem}
}
```

---

## 🙏 致谢

Brain-Mem 受到数十年认知科学和神经科学研究的启发。特别感谢那些使这一切成为可能的研究人员：

- Fergus Craik & Robert Lockhart（加工水平理论）
- Richard Atkinson & Richard Shiffrin（多存储模型）
- Hermann Ebbinghaus（遗忘曲线）
- Robert Stickgold & Matthew Walker（睡眠巩固）
- James McGaugh（情绪记忆）

---

<p align="center">
  <em>"大脑不是一个需要被填满的容器，而是一团需要被点燃的火焰。" — 普鲁塔克</em>
</p>

<p align="center">
  <strong>用 🧠 为像人类一样记忆的 AI 智能体而构建</strong>
</p>
