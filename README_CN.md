<p align="center">
  <h1 align="center">🧠 Brain-Mem</h1>
  <p align="center"><strong>基于认知科学的AI智能体记忆系统</strong></p>
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

## 概述

Brain-Mem 是一个生产级记忆系统，忠实模拟**人脑**处理、存储、巩固和检索记忆的方式。与简单的向量数据库或键值存储不同，Brain-Mem 实现了认知科学机制，包括选择性编码、睡眠巩固、间隔重复、情绪共鸣、前瞻性记忆和自然遗忘。

**核心优势：**
- 🧠 **认知架构** — 将大脑区域（海马体、前额叶皮层、杏仁核）映射到系统组件
- 🏗️ **分层存储** — 知识图谱存储认知，文件系统存储详细日志
- 🔄 **睡眠巩固** — 批处理强化重要记忆并修剪噪音
- 🎯 **多路径检索** — 5种检索策略，支持情绪共鸣和失败补偿
- ⏰ **前瞻性记忆** — 基于时间和事件的未来提醒
- 📊 **间隔重复** — 自动安排复习以防止遗忘
- 🔗 **实体解析** — LLM驱动的名称映射和关系对齐

## 为什么选择 Brain-Mem？

大多数AI记忆系统将记忆视为扁平数据库：存储一切，按相似度检索。人脑的工作方式根本不同：

| 人脑机制 | Brain-Mem 实现 |
|---|---|
| **选择性编码** — 并非所有信息都被存储 | Perceiver过滤噪音，Evaluator按重要性筛选 |
| **睡眠巩固** — 记忆在休息时强化 | Consolidator批处理buffer→graph，解决冲突 |
| **多路径检索** — 通过名称、情绪、上下文回忆 | 5种检索策略 + 情绪共鸣加权 |
| **自然遗忘** — 防止信息过载 | 基于重要性加权的半衰期衰减机制 |
| **前瞻性记忆** — "当X发生时提醒我" | 基于时间和事件的触发器存储在图谱中 |
| **跨会话连续性** — 永不从零开始 | 会话摘要桥接对话 |

## 快速开始

### 前置要求

- Docker & Docker Compose
- OpenAI兼容的LLM API（OpenAI、Azure、本地模型如vLLM/Ollama）
- 最低2GB内存，推荐4GB

### 安装

```bash
# 克隆仓库
git clone https://github.com/yourusername/brain-mem.git
cd brain-mem

# 复制并配置
cp config.yaml.example config.yaml
# 编辑config.yaml，填入你的LLM API凭证

# 启动服务
docker compose up -d

# 验证健康状态
curl http://localhost:8100/health
```

**服务地址：**
- Brain-Mem API: `http://localhost:8100`
- Neo4j浏览器: `http://localhost:7474` (用户名: `neo4j`, 密码: 来自`NEO4J_PASSWORD`环境变量)


### 配置

编辑 `config.yaml`:

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
# 添加到crontab（每天凌晨1:30运行）
30 1 * * * curl -X POST http://localhost:8100/hooks/consolidate \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"default","user_id":"your_user"}' \
  >> /var/log/brain-mem-consolidation.log 2>&1
```

## 系统架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     输入消息                                  │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────▼────────────────┐
         │  👁️ Perceiver                  │  过滤噪音，分类信息
         │  (感觉皮层 + 丘脑)             │  路由：认知 vs 日志
         └───────────────┬────────────────┘
                         │
         ┌───────────────▼────────────────┐
         │  🧪 Evaluator                  │  评分重要性、新颖性
         │  (前额叶 + 杏仁核)             │  长期存储门控
         └───────────────┬────────────────┘
                         │
         ┌───────────────▼────────────────┐
         │  🏗️ Encoder                    │  实体解析
         │  (海马体)                      │  名称映射、关系对齐
         └─────┬──────────────────┬───────┘
               │                  │
    ┌──────────▼─────┐   ┌───────▼────────┐
    │ 📦 Buffer       │   │ 📝 文件日志     │
    │ (SQLite)        │   │ (Markdown)     │
    └──────────┬──────┘   └────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │  💤 Consolidator                    │  睡眠巩固
    │  (Buffer → Graph)                   │  间隔重复
    └──────────┬──────────────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │  📊 知识图谱 (Neo4j)                 │  长期记忆
    │  + 向量索引                          │  实体 + 关系
    └─────────────────────────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │  🔍 Retriever                       │  多路径召回
    │  (5种策略 + 情绪)                   │  上下文合成
    └─────────────────────────────────────┘
```

### 组件映射

| 大脑区域 | 组件 | 功能 |
|---|---|---|
| **感觉皮层 + 丘脑** | Perceiver | 过滤噪音，分类信息类型 |
| **前额叶皮层 + 杏仁核** | Evaluator | 评分重要性、新颖性、情绪意义 |
| **海马体** | Encoder | 实体生命周期、名称解析、关系映射 |
| **睡眠巩固** | Consolidator | Buffer→Graph转移、冲突解决、间隔重复 |
| **长期记忆** | Neo4j图谱 | 持久化知识存储，支持向量搜索 |
| **工作记忆** | Working Memory | 每会话上下文缓存 |
| **前瞻性记忆** | Prospective Checker | 面向未来的提醒 |


## 核心特性

### 1. 分层存储架构

大脑不会用相同方式存储购物清单和人生决策。Brain-Mem 使用三层存储模型：

**知识图谱 (Neo4j)** — 高层认知
- 目标、决策、关系、里程碑、洞察
- 重要性 ≥ 5.0 的实体
- 向量嵌入支持语义搜索

**文件系统 (Markdown)** — 详细日志
- 饮食记录、运动日志、面试笔记
- 交易记录、学习日志
- 按类别和日期组织

**缓冲区 (SQLite)** — 短期暂存
- 等待巩固的编码记忆单元
- 跨会话连续性的会话摘要
- 类型过滤读取（记忆 vs 摘要）

**示例：**
```
用户: "我早餐吃了个苹果"

❌ 没有分层存储:
   → 创建实体: 苹果、用户、早餐水果习惯
   → 图谱被琐碎食物项污染

✅ 有分层存储:
   → 追加到 memory/logs/diet/2026-03-22.md
   → 更新图谱: DietPlan.last_diet_log = "2026-03-22"
   → 图谱保持清洁，细节得以保留
```

### 2. 实体解析与名称映射

编码器不会盲目创建节点，而是遵循严格的生命周期：

1. **层级标签分配** — 使用两级标签树分类实体
2. **同类型检索** — 搜索具有匹配标签的现有节点
3. **LLM解析** — 决定：`create`（创建）、`merge`（合并）或 `update`（更新）
4. **名称映射** — 构建 `原始名称 → 最终名称` 映射
5. **关系对齐** — 将映射应用于所有关系
6. **嵌入生成** — 自动生成向量嵌入

**示例：**
```
用户: "凡哥是我同事"
→ "凡哥" 解析为现有节点 "刘凡"
→ 关系修正: from_name="刘凡" (而非 "凡哥")
→ 无孤立引用
```

### 3. 多路径检索

人类记忆检索不是单一机制。Brain-Mem 实现5种策略：

| 路径 | 策略 | 使用场景 |
|---|---|---|
| **A** | 精确名称匹配 | 直接实体查找 |
| **B** | 别名匹配 | "那个AI项目" → 匹配项目别名 |
| **C** | 模糊关键词 | 部分匹配、相关术语 |
| **D** | 休眠重激活 | 唤醒旧记忆 |
| **E** | 向量语义 | 基于嵌入的意义检索 |

**附加机制：**
- **情绪共鸣** — 情绪动态调整评分权重
- **失败补偿** — 结果不足时自动扩展到3跳图遍历


### 4. 睡眠巩固

模拟大脑睡眠阶段的记忆巩固，包含12个步骤：

1. **读取缓冲区** — 获取未归档的记忆单元
2. **实体更新** — 在图谱中创建/合并/更新节点
3. **关系创建** — 构建知识图谱连接
4. **嵌入生成** — 为新节点自动生成向量
5. **模式发现** — LLM发现跨事件模式
6. **冲突解决** — 解决矛盾记忆
7. **孤儿修复** — 连接孤立节点
8. **创造性重组** — 发现非显而易见的洞察
9. **图谱清理** — 合并重复、抑制噪音
10. **隐含关系** — 推断缺失连接
11. **记忆衰减** — 应用遗忘曲线
12. **间隔重复** — 为重要记忆安排复习

**触发方式：** 每日定时任务（推荐：凌晨1:30）

### 5. 间隔重复

使用艾宾浩斯遗忘曲线防止重要记忆淡化：

- **复习间隔：** 1 → 3 → 7 → 21 天，然后翻倍
- **自动强化：** Consolidator直接提升 `retrieval_strength`
- **抗衰减：** 重要节点（importance ≥ 6.0）定期复习
- **无需用户操作：** 系统自动维护记忆强度

### 6. 前瞻性记忆

面向未来的提醒，支持两种触发类型：

**基于时间：**
```
"明天下午3点提醒我给客户打电话"
→ 存储trigger_time，在指定时间触发
```

**基于事件：**
```
"当我提到项目时，提醒我更新时间线"
→ 查询匹配触发关键词时触发
→ 支持重复次数（1=一次性，0=无限，N=有限次数）
```

## API 参考

### 核心端点

| 端点 | 方法 | 描述 |
|---|---|---|
| `/health` | GET | 健康检查和版本信息 |
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
|---|---|---|
| `/hooks/status/session-start` | GET | 检查session-start hook日志 |
| `/hooks/status/before-query` | GET | 检查before-query hook日志 |
| `/hooks/status/after-response` | GET | 检查after-response hook日志 |
| `/hooks/status/session-end` | GET | 检查session-end hook日志 |


### 示例：完整会话生命周期

```bash
# 1. 启动会话
curl -X POST http://localhost:8100/hooks/session-start \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "user_profile": {"name": "Alice", "role": "工程师"}
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
    "user_message": "我决定转向AI研究",
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

## 项目结构

```
brain-mem/
├── server/
│   ├── app.py                      # FastAPI应用 & 端点
│   ├── activity_log.py             # 活动日志
│   ├── engine/
│   │   ├── perceiver.py            # 👁️ 过滤 & 分类
│   │   ├── evaluator.py            # 🧪  评估重要性
│   │   ├── encoder.py              # 🏗️ 实体生命周期
│   │   ├── retriever.py            # 🔍 多路径检索
│   │   ├── consolidator.py         # 💤 睡眠巩固
│   │   ├── working_memory.py       # 🎯 会话上下文
│   │   ├── prospective_checker.py  # ⏰ 未来提醒
│   │   ├── profile_updater.py      # 👤 用户档案
│   │   ├── log_writer.py           # 📝 文件日志
│   │   ├── embedding_client.py     # 🔢 嵌入
│   │   └── llm_client.py           # 🤖 LLM客户端
│   ├── storage/
│   │   ├── graph.py                # Neo4j操作
│   │   ├── buffer.py               # SQLite缓冲区
│   │   ├── tag_dict.py             # 标签层级
│   │   └── user_profile.py         # 档案存储
│   └── models/
│       ├── node.py                 # 节点模型
│       └── relation.py             # 关系模型
├── openclaw-plugin/
│   └── index.ts                    # OpenClaw集成
├── config.yaml.example             # 配置模板
├── docker-compose.yml              # Docker部署
├── Dockerfile                      # 容器构建
├── requirements.txt                # 依赖
└── README_CN.md                    # 中文文档
```

## 技术栈

- **运行时：** Python 3.11+ / FastAPI / Uvicorn
- **图数据库：** Neo4j 5.x（原生向量索引）
- **缓冲区：** SQLite（零配置，类型过滤）
- **LLM：** OpenAI兼容API
- **嵌入：** text-embedding-3-small（1536维）
- **插件：** TypeScript（OpenClaw）

## 对比

| 特性 | Brain-Mem | mem0 | Letta |
|---|:---:|:---:|:---:|
| 认知架构 | ✅ | ❌ | ❌ |
| 知识图谱 | ✅ Neo4j | ❌ | ❌ |
| 分层存储 | ✅ | ❌ | ❌ |
| 实体解析 | ✅ LLM | ❌ | ❌ |
| 多路径检索 | ✅ 5路径 | ❌ | ❌ |
| 睡眠巩固 | ✅ | ❌ | ❌ |
| 间隔重复 | ✅ | ❌ | ❌ |
| 情绪共鸣 | ✅ | ❌ | ❌ |
| 前瞻性记忆 | ✅ | ❌ | ❌ |
| 自然遗忘 | ✅ | ❌ | ❌ |
| 会话摘要 | ✅ | ❌ | ✅ |
| 多租户 | ✅ | ✅ | ❌ |


## 开发

### 本地部署

```bash
# 克隆仓库
git clone https://github.com/yourusername/brain-mem.git
cd brain-mem

# 安装依赖
pip install -r requirements.txt

# 启动Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:5

# 配置
cp config.yaml.example config.yaml
# 编辑config.yaml

# 运行服务器
python -m uvicorn server.app:app --reload --port 8100
```

### 环境变量

```bash
# 使用环境变量覆盖config.yaml
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_PASSWORD="your_password"
export LLM_API_KEY="sk-..."
```

## OpenClaw 集成

Brain-Mem 包含 OpenClaw 插件，可无缝集成：

```typescript
// openclaw-plugin/index.ts
// Hooks: session-start, before-query, after-response, session-end
```

在 OpenClaw 中安装：
```bash
cd openclaw-plugin
npm install
# 在 OpenClaw 设置中配置
```

## 故障排除

**Neo4j 连接失败：**
```bash
# 检查 Neo4j 是否运行
docker ps | grep neo4j
# 验证 config.yaml 中的凭证
```

**嵌入生成缓慢：**
```bash
# 检查嵌入 API 端点
curl -X POST https://api.openai.com/v1/embeddings \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"input":"test","model":"text-embedding-3-small"}'
```

**记忆未巩固：**
```bash
# 检查巩固日志
curl http://localhost:8100/logs?n=100 | grep consolidation
# 手动触发
curl -X POST http://localhost:8100/hooks/consolidate \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"default","user_id":"your_user"}'
```

## 许可证

MIT License - 详见 [LICENSE](LICENSE) 文件。

## 引用

如果您在研究中使用 Brain-Mem，请引用：

```bibtex
@software{brain_mem_2026,
  title = {Brain-Mem: A Cognitive Science-Inspired Memory System for AI Agents},
  author = {Your Name},
  year = {2026},
  url = {https://github.com/yourusername/brain-mem}
}
```

---

<p align="center">
  <em>"大脑不是一个需要被填满的容器，而是一团需要被点燃的火焰。" — 普鲁塔克</em>
</p>


