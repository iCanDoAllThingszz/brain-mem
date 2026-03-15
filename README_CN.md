<p align="center">
  <h1 align="center">🧠 Brain-Mem</h1>
  <p align="center"><strong>基于认知科学的 AI Agent 记忆系统</strong></p>
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

Brain-Mem 模拟人脑处理、存储、巩固和检索记忆的完整过程，为 AI Agent 提供一套生产级记忆服务。不同于简单的键值存储或向量检索，Brain-Mem 忠实映射了认知科学中的核心机制：选择性编码、睡眠巩固、自然遗忘、情绪共鸣、前瞻性记忆。

## 为什么需要 Brain-Mem？

大多数 AI Agent 记忆系统把记忆当作扁平数据库：存一切，按相似度检索。但人脑的工作方式完全不同：

- **不是所有信息都会被存储** — 大脑主动过滤和评估输入信息
- **记忆在睡眠中巩固** — 重要记忆增强，琐碎记忆衰退
- **检索是多通路的** — 你可以通过名字、联想、情绪、上下文回忆事物
- **遗忘是特性而非缺陷** — 防止信息过载，保持记忆的时效性
- **未来意图会持久化** — "X发生时提醒我做Y"是真实的记忆类型

Brain-Mem 实现了以上所有机制。

## 架构：大脑 ↔ 系统映射

```
                    ┌─────────────────────────────────────────────┐
                    │              输入消息                         │
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  👁️ 感知器 Perceiver（感觉皮层 + 丘脑）      │
                    │  过滤噪音，分类信息，结构化改写               │
                    │  路由：认知 → 图谱 | 日志 → 文件              │
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  🧪 评估器 Evaluator（前额叶 + 杏仁核）      │
                    │  评估记忆价值：重要性、新颖性、情绪显著性     │
                    │  决定是否进入长期记忆                         │
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  🏗️ 编码器 Encoder（海马体）                  │
                    │  实体生命周期管理：创建 / 合并 / 更新          │
                    │  代词消解，去重，自动生成向量嵌入              │
                    └──────┬───────────────────────┬──────────────┘
                           │                       │
              ┌────────────▼─────────┐  ┌─────────▼──────────────┐
              │  📊 知识图谱          │  │  📝 文件日志            │
              │  (Neo4j + 向量索引)  │  │  饮食/运动/交易/面试    │
              │  目标、决策、关系     │  │  详细的每日记录          │
              └────────────┬─────────┘  └─────────┬──────────────┘
                           │                       │
              ┌────────────▼───────────────────────▼──────────────┐
              │  💤 巩固器 Consolidator（睡眠巩固）                │
              │  间隔重复、创造性重组、图谱清洁、干扰遗忘          │
              │  每日定时执行（cron）                               │
              └───────────────────────────────────────────────────┘

              ┌───────────────────────────────────────────────────┐
              │  🔍 检索器 Retriever（多通路召回）                  │
              │  5种策略：精确 → 别名 → 模糊 → 休眠唤醒 → 向量语义│
              │  情绪共鸣加权 + 检索失败补偿                       │
              └───────────────────────────────────────────────────┘

              ┌───────────────────────────────────────────────────┐
              │  🎯 工作记忆 Working Memory（会话上下文）           │
              │  活跃目标、待触发提醒、情绪基线                    │
              └───────────────────────────────────────────────────┘

              ┌───────────────────────────────────────────────────┐
              │  ⏰ 前瞻检查器 Prospective Checker（未来记忆）     │
              │  基于时间和事件的触发器                             │
              └───────────────────────────────────────────────────┘
```


## 组件详解

| 脑区 | 组件 | 文件 | 功能 |
|---|---|---|---|
| 感觉皮层 + 丘脑 | **感知器 Perceiver** | `perceiver.py` | 过滤噪音（寒暄、指令），将信息分类为认知型或日志型，结构化改写原始消息 |
| 前额叶 + 杏仁核 | **评估器 Evaluator** | `evaluator.py` | 深度评估记忆价值，打分维度：重要性、新颖性、情绪显著性。日志类信息自动通过 |
| 海马体 | **编码器 Encoder** | `encoder.py` | LLM驱动的实体生命周期管理：基于标签分组检索同类实体，一次LLM调用决定创建/合并/更新 |
| 短期缓冲区 | **缓冲区 Buffer** | `buffer.py` | 基于SQLite的临时存储，支持向量嵌入，在巩固前暂存近期记忆 |
| 睡眠巩固 | **巩固器 Consolidator** | `consolidator.py` | 每日批处理：间隔重复调度（1→3→7→21天）、创造性重组、LLM驱动的图谱清洁 |
| 记忆检索 | **检索器 Retriever** | `retriever.py` | 5通路检索 + 情绪共鸣加权 + 检索失败补偿，将检索到的记忆片段合成为事实性上下文 |
| 工作记忆 | **工作记忆 Working Memory** | `working_memory.py` | 会话级上下文缓存：活跃目标、待触发提醒、情绪基线 |
| 前瞻性记忆 | **前瞻检查器 Prospective Checker** | `prospective_checker.py` | 面向未来的记忆：基于时间（"下午3点提醒"）和基于事件（"X发生时提醒"）的触发器 |
| 嵌入系统 | **嵌入客户端 Embedding Client** | `embedding_client.py` | 异步向量生成 + LRU缓存（1000条），驱动向量语义检索 |
| 日志系统 | **日志写入器 Log Writer** | `log_writer.py` | 按类别写入文件日志（饮食/运动/面试/交易/学习），同时维护图谱索引指针 |

## 核心特性

### 1. 分层存储（v3 架构）

大脑不会用存储人生决策的方式来存储购物清单。Brain-Mem 也是如此。

- **知识图谱（Neo4j）** — 高层认知：目标、决策、人际关系、里程碑、洞察
- **文件系统** — 详细日志：饮食记录、运动日志、面试笔记、交易记录、学习日志
- **图谱 ↔ 文件关联** — 图谱节点通过 `log_path` 指向日志文件，支持从认知下钻到细节
- **效果**：图谱保持干净和有意义，不会被"苹果"、"牛肉面"等食物实体污染

```
用户："早上我吃了一个苹果"

❌ 没有分层存储：
   → 创建实体：苹果、用户、早餐水果习惯
   → 图谱被食物条目污染

✅ 有分层存储：
   → 追加到 memory/logs/diet/2026-03-14.md："- 早餐：苹果"
   → 更新图谱：减肥计划.last_diet_log = "2026-03-14"
   → 图谱保持干净，细节保存在文件中
```

### 2. 智能编码（实体生命周期管理）

编码器不会盲目创建新节点，而是遵循严格的生命周期：

1. **标签分组** — 按语义标签对实体分类
2. **同类检索** — 搜索具有匹配标签的现有节点
3. **LLM决策** — 一次LLM调用决定：`create`（新建）、`merge`（合并到已有）、`update`（更新已有）
4. **代词消解** — "我" → 实际用户名（硬编码兜底 + LLM驱动）
5. **嵌入生成** — 编码时自动生成向量嵌入

预算：**每次编码操作仅1次LLM调用** — 高效设计。

### 3. 多通路检索（5种策略）

人类的记忆检索不是单一机制。你可能通过名字、联想或模糊的感觉回忆起某件事。Brain-Mem 实现了5条检索通路：

| 通路 | 策略 | 适用场景 |
|---|---|---|
| A | **精确名称匹配** | 直接实体查找 |
| B | **别名匹配** | "那个AI项目" → 匹配某个命名项目的别名 |
| C | **模糊关键词搜索** | 部分匹配、相关词汇 |
| D | **休眠节点唤醒** | 重新激活长期未访问的节点 |
| E | **向量语义搜索** | 基于语义的嵌入检索 |

附加机制：
- **情绪共鸣** — 非中性情绪动态调整评分权重（相关性×0.4 + 情绪×0.2，而非默认的×0.5 / ×0.1）
- **检索失败补偿** — 初始搜索结果不足时，自动扩展到3跳图遍历
- **多跳遍历** — 默认1-2跳，补偿时扩展


### 4. 认知科学特性

这些不是噱头 — 每一项都映射到真实的认知机制，并有具体的工程实现：

| 机制 | 脑科学基础 | 实现方式 |
|---|---|---|
| **间隔重复** | 艾宾浩斯遗忘曲线 | 复习间隔：1→3→7→21天，之后翻倍。巩固器根据访问模式调度下次复习 |
| **创造性重组** | 睡眠期洞察生成 | 巩固期间，LLM发现记忆之间的非显性关联（最多2次尝试，temperature=0.7，置信度≥0.5） |
| **记忆再巩固** | 回忆时的记忆更新 | 用户纠正自动更新已有记忆，无需评估门控。目标实体不存在时自动创建 |
| **干扰遗忘** | 竞争性记忆痕迹 | 相似记忆自然竞争，较弱的痕迹在更强替代品存在时加速衰退 |
| **自然衰减** | 基于时间的遗忘 | 未使用的记忆通过 `decay_factor` 逐渐降低检索强度，保持记忆的时效性 |
| **情绪共鸣** | 杏仁核调节 | 带情绪标签的记忆获得检索优先级，非中性情绪动态调整评分权重 |
| **前瞻性记忆** | 未来意图编码 | 基于时间（"下午3点提醒"）和基于事件（"X发生时提醒"）的触发器，直接写入图谱 |
| **动机性遗忘** | 抑制机制 | 节点可被抑制（隐藏但不删除）— 可恢复，但退出主动检索 |

### 5. LLM驱动的图谱清洁

保持知识图谱的整洁很难。Brain-Mem 用LLM智能替代脆弱的硬编码规则：

- **巩固器批量审查**图谱节点（每批最多30个节点，每次巩固最多3次LLM调用）
- **决策类型**：合并重复、抑制噪音、保留不确定
- **反误杀优先**：当LLM返回"不确定"时 → **始终保留节点**。误删比冗余更糟糕。
- **唯一的硬编码规则**：代词 → 用户名映射。其他一切由LLM决定。

### 6. 工作记忆

每个对话会话拥有独立的工作记忆上下文：

- **活跃目标** — 用户当前正在推进的事项
- **待触发提醒** — 等待激活的前瞻性记忆触发器
- **情绪基线** — 当前情绪状态，用于共鸣评分
- 在 `session-start` 时加载，为感知器、评估器和检索器提供上下文

### 7. 向量检索

基于 Neo4j 5.x 原生向量索引构建 — 无需额外的向量数据库：

- **图谱节点**：1536维嵌入的余弦相似度搜索
- **缓冲区记录**：Numpy暴力余弦计算（<1000条时最优，无ANN开销）
- **向量字段组合**：图谱使用 `"name: summary"` 拼接；缓冲区使用感知器改写文本
- **自动生成**：编码时创建嵌入；提供回填端点处理已有节点

## 与其他系统的对比

| 特性 | Brain-Mem | mem0 | Letta (MemGPT) |
|---|:---:|:---:|:---:|
| 认知科学架构 | ✅ 完整管线 | ❌ | ❌ |
| 知识图谱存储 | ✅ Neo4j | ❌ 键值存储 | ❌ |
| 分层存储（图谱+文件） | ✅ | ❌ | ❌ |
| 多通路检索（5种策略） | ✅ | ❌ 仅相似度 | ❌ 仅相似度 |
| 向量语义搜索 | ✅ Neo4j原生 | ✅ | ✅ |
| 睡眠巩固 | ✅ 每日定时 | ❌ | ❌ |
| 间隔重复 | ✅ Anki风格 | ❌ | ❌ |
| 创造性重组 | ✅ LLM驱动 | ❌ | ❌ |
| 情绪共鸣 | ✅ 动态权重 | ❌ | ❌ |
| 前瞻性记忆 | ✅ 时间+事件触发 | ❌ | ❌ |
| 自然遗忘/衰减 | ✅ | ❌ | ❌ |
| 记忆再巩固 | ✅ | ❌ | ❌ |
| 实体生命周期管理 | ✅ LLM驱动 | ❌ | ❌ |
| 图谱自动清洁 | ✅ LLM驱动 | ❌ | ❌ |
| 工作记忆（会话级） | ✅ | ❌ | ✅ |
| 多租户支持 | ✅ | ✅ | ❌ |


## API 参考

| 端点 | 方法 | 描述 |
|---|---|---|
| `/health` | GET | 健康检查和版本信息 |
| `/logs` | GET | 查看最近活动日志（`?n=50`） |
| `/hooks/session-start` | POST | 初始化会话，加载工作记忆 |
| `/hooks/before-query` | POST | 为查询检索相关记忆 |
| `/hooks/after-response` | POST | 处理并编码对话中的新记忆 |
| `/hooks/consolidate` | POST | 触发记忆巩固（每日定时任务） |
| `/hooks/backfill-embeddings` | POST | 一次性为无嵌入的节点生成向量 |

### 示例：检索记忆

```bash
# 启动会话
curl -X POST http://localhost:8100/hooks/session-start \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "default", "user_id": "alice", "session_id": "sess-001"}'

# 带记忆上下文的查询
curl -X POST http://localhost:8100/hooks/before-query \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "query": "我的减肥计划是什么？"
  }'
# 返回: {"code": 0, "data": {"context": "Alice的减肥计划目标是每日1600大卡..."}}
```

### 示例：编码记忆

```bash
curl -X POST http://localhost:8100/hooks/after-response \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "user_message": "我决定下个月跳槽",
    "assistant_message": "好的，我会帮你准备。"
  }'
```

## 快速开始

### 方式一：Docker Compose（推荐）

```bash
git clone https://github.com/iCanDoAllThingszz/brain-mem.git
cd brain-mem
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入你的 LLM API 凭证和 Neo4j 密码
docker compose up -d
# 服务地址：http://localhost:8100
```

### 方式二：手动部署

```bash
git clone https://github.com/iCanDoAllThingszz/brain-mem.git
cd brain-mem
cp config.yaml.example config.yaml
# 编辑 config.yaml

pip install -r requirements.txt

# 启动 Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:5

# 启动 Brain-Mem
python -m uvicorn server.app:app --host 0.0.0.0 --port 8100
```

### 配置巩固定时任务

```bash
# 每天凌晨1:30执行巩固（根据时区调整）
echo '30 17 * * * curl -s -X POST http://localhost:8100/hooks/consolidate \
  -H "Content-Type: application/json" \
  -d '"'"'{"tenant_id":"default","user_id":"your_user_id"}'"'"' \
  >> /path/to/consolidation.log 2>&1' | crontab -
```

## 项目结构

```
brain-mem/
├── server/
│   ├── app.py                    # FastAPI 应用，所有 API 端点
│   ├── activity_log.py           # 活动日志工具
│   ├── engine/
│   │   ├── perceiver.py          # 👁️ 感觉皮层 — 过滤与分类
│   │   ├── evaluator.py          # 🧪 前额叶 — 评估记忆价值
│   │   ├── encoder.py            # 🏗️ 海马体 — 实体生命周期管理
│   │   ├── retriever.py          # 🔍 多通路记忆检索
│   │   ├── consolidator.py       # 💤 睡眠巩固与图谱清洁
│   │   ├── working_memory.py     # 🎯 会话级上下文缓存
│   │   ├── prospective_checker.py# ⏰ 未来记忆触发器
│   │   ├── log_writer.py         # 📝 分类文件日志
│   │   ├── embedding_client.py   # 🔢 异步嵌入 + LRU缓存
│   │   └── llm_client.py         # 🤖 共享LLM客户端
│   ├── storage/
│   │   ├── graph.py              # Neo4j 图操作 + 向量索引
│   │   ├── buffer.py             # SQLite 缓冲区存储
│   │   └── tag_dict.py           # 标签字典，用于实体分组
│   └── models/
│       ├── node.py               # MemoryNode 数据模型
│       └── relation.py           # Relation 数据模型
├── openclaw-plugin/
│   └── index.ts                  # OpenClaw 集成插件
├── benchmark/
│   └── run_benchmark.py          # 自动化测试套件（6个维度）
├── docs/
│   └── V3-DESIGN.md             # v3 分层存储设计文档
├── config.yaml.example           # 配置模板
├── docker-compose.yml            # 一键部署
├── Dockerfile                    # 容器构建
├── demo.py                       # 完整管线演示脚本
├── requirements.txt              # Python 依赖
└── README_CN.md                  # 你在这里
```

## 配置说明

将 `config.yaml.example` 复制为 `config.yaml` 并填入你的凭证：

```yaml
neo4j:
  uri: "bolt://localhost:7687"
  user: "neo4j"
  password: "your_password"

llm:
  base_url: "https://api.openai.com/v1"  # 任何 OpenAI 兼容 API
  api_key: "your_api_key"
  model: "gpt-4o"

embedding:
  base_url: "https://api.openai.com/v1"
  api_key: "your_api_key"
  model: "text-embedding-3-small"
```

> ⚠️ `config.yaml` 已加入 gitignore，永远不要提交凭证。

## 技术栈

- **运行时**：Python 3.11+ / FastAPI / Uvicorn
- **图数据库**：Neo4j 5.x（知识图谱 + 原生向量索引）
- **缓冲区**：SQLite（轻量级，零配置）
- **LLM**：任何 OpenAI 兼容 API
- **嵌入**：任何嵌入 API（默认维度：1536）

## 路线图

- [ ] Web UI 图谱可视化与管理
- [ ] 多用户协作记忆
- [ ] 自定义感知器/评估器规则的插件市场
- [ ] 流式检索，支持实时应用
- [ ] 记忆导入/导出（JSON、Markdown）
- [ ] Prometheus 指标与 Grafana 仪表盘

## 许可证

[MIT](LICENSE)

---

<p align="center">
  <em>"大脑不是一个需要被填满的容器，而是一束需要被点燃的火焰。" — 普鲁塔克</em>
</p>
