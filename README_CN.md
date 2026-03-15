<div align="center">

# 🧠 Brain-Mem

**基于认知科学的 AI Agent 记忆系统**

*不只是存储——一个会编码、遗忘、做梦、成长的大脑。*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Neo4j 5.x](https://img.shields.io/badge/Neo4j-5.x-008CC1.svg)](https://neo4j.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)

[English](README.md) | **中文**

</div>

---

## 为什么需要 Brain-Mem？

大多数 AI 记忆系统本质上是美化的键值存储：存一切、按关键词检索、完事。

人类记忆不是这样工作的。我们**选择性编码**重要信息、用**情绪加权**体验、在**睡眠中巩固**记忆、**自然遗忘**不重要的事、还能**创造性重组**碎片产生新洞察。

Brain-Mem 将这些认知科学原理带给 AI Agent：

| 能力 | 认知科学基础 | 作用 |
|:-----|:-----------|:-----|
| 选择性编码 | 海马体门控 | 只编码新颖、相关的信息——噪声直接丢弃 |
| 情绪共鸣 | 心境一致性记忆 | 悲伤语境？检索共情记忆 + 鼓励性记忆 |
| 睡眠巩固 | 记忆巩固理论 | 每夜定时去重、发现模式、生成洞察 |
| 自然遗忘 | 艾宾浩斯曲线 | 不重要的记忆衰减；重要的通过间隔重复保持 |
| 记忆重巩固 | 记忆更新理论 | "其实那次面试还不错" → 原地修正已存储的记忆 |
| 前瞻性记忆 | 未来意图 | 时间/事件触发器："下次聊到 X 时提醒我 Y" |
| 创造性重组 | REM 睡眠做梦 | 随机记忆碎片组合 → 偶尔产生有价值的新洞察 |
| 向量检索 | 语义相似度 | 图遍历 + 向量搜索混合检索，召回更鲁棒 |

## 架构

```
用户消息
  │
  ▼
┌──────────┐    ┌──────────┐    ┌──────────┐
│ 感知器   │───▶│ 评估器   │───▶│ 编码器   │
│ (丘脑)   │    │(前额叶)  │    │(海马体)  │
└──────────┘    └──────────┘    └────┬─────┘
 分类 & 改写     评分新颖度          │ 实体 + 关系
                 & 相关度            │
                                    ▼
                             ┌─────────────┐   每夜巩固   ┌─────────────┐
                             │   缓冲区    │────────────▶│  巩固器     │
                             │  (SQLite)   │             │  (睡眠)     │
                             └─────────────┘             └──────┬──────┘
                                    ▲                           │
                                    │                           ▼
                             ┌─────────────┐             ┌─────────────┐
                             │   检索器    │◀───────────▶│   Neo4j     │
                             │ (多路径)    │  图 + 向量   │  (长期记忆)  │
                             └─────────────┘             └─────────────┘
```

**核心管线：** 感知器 → 评估器 → 编码器 → 缓冲区 → 巩固器 → 知识图谱

**检索策略：** 5 路径（精确匹配 → 别名 → 模糊 → 休眠节点 → 向量语义）

**分层存储：** 按信息类型路由到不同存储：

| 输入 | 分类 | 存储位置 |
|:----|:-----|:--------|
| "我决定跳槽" | `cognition` | 知识图谱（实体 + 关系） |
| "中午吃了沙拉300大卡" | `log_diet` | Markdown 文件 + 缓冲区索引 |
| "跑了5公里" | `log_exercise` | Markdown 文件 + 缓冲区索引 |
| "不对，面试其实很好" | `reconsolidation` | 图谱更新（修正已有节点） |
| "明天提醒我开会" | `prospective` | 图谱（触发器节点） |
| "忘掉这个人" | `forget` | 图谱（节点抑制，不再检索） |
| "嗯嗯" | `noise` | 丢弃 |

## 快速开始

### 环境要求

- Python 3.11+
- Neo4j 5.x（推荐 Docker）
- 任意 OpenAI 兼容的 LLM API

### 安装

```bash
git clone https://github.com/iCanDoAllThingszz/brain-mem.git
cd brain-mem
pip install -r requirements.txt
```

### 启动 Neo4j

```bash
docker run -d --name neo4j-memory \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:5
```

### 配置

```bash
cp config.yaml.example config.yaml
```

编辑 `config.yaml`：

```yaml
llm:
  base_url: "https://api.openai.com/v1"  # 任意 OpenAI 兼容端点
  model: "gpt-4o"
  api_key: "sk-..."

storage:
  neo4j:
    uri: "bolt://localhost:7687"
    user: "neo4j"
    password: "your-password"
  buffer:
    path: "./data/buffer.db"
```

### 运行

```bash
python -m uvicorn server.app:app --host 0.0.0.0 --port 8100
```

### 配置每夜巩固

```bash
# 每天凌晨 1:00 执行巩固
(crontab -l 2>/dev/null; echo "0 1 * * * curl -s -X POST http://localhost:8100/hooks/consolidate \
  -H 'Content-Type: application/json' \
  -d '{\"tenant_id\":\"default\",\"user_id\":\"your-user\"}'") | crontab -
```

## API 参考

### Hooks（集成接口）

| 方法 | 端点 | 说明 |
|:----|:-----|:-----|
| `POST` | `/hooks/session-start` | 初始化会话工作记忆 |
| `POST` | `/hooks/before-query` | LLM 调用前检索相关记忆 |
| `POST` | `/hooks/after-response` | 将用户消息编码为记忆 |
| `POST` | `/hooks/session-end` | 清理会话状态 |
| `POST` | `/hooks/consolidate` | 触发睡眠巩固周期 |
| `POST` | `/hooks/check-prospective` | 检查时间/事件触发器 |
| `POST` | `/hooks/backfill-embeddings` | 一次性：为已有节点生成向量 |

### 使用示例

```python
import httpx

BASE = "http://localhost:8100"
CTX = {"tenant_id": "default", "user_id": "alice", "session_id": "s1"}

# 编码一条消息
httpx.post(f"{BASE}/hooks/after-response", json={
    **CTX,
    "user_message": "下周二去 Google 面试",
    "assistant_response": "加油！需要我帮你准备吗？"
})

# 检索记忆
resp = httpx.post(f"{BASE}/hooks/before-query", json={
    **CTX,
    "query": "我最近有什么面试？"
})
print(resp.json()["data"]["context"])
# → "alice 下周二有一场 Google 的面试。"
```

## 记忆衰减模型

基于艾宾浩斯遗忘曲线，不同类型的记忆以不同速率衰减：

```
有效半衰期 = 基础天数 × (1 + 重要度/10) × 区域系数

区域系数：
  情景记忆 = 0.5   (事件消退快)
  语义记忆 = 2.0   (事实持久)
  程序记忆 = 3.0   (技能最持久)
  情绪记忆 = 1.0   (基准线)
```

## 向量检索

Brain-Mem 使用图遍历 + 向量相似度的混合检索：

- **Neo4j 向量索引**：MemoryNode 上的原生向量索引（1536维，余弦相似度）
- **缓冲区向量搜索**：NumPy 暴力余弦计算（短期缓冲区 <1000 条时最优）
- **Embedding**：支持任意 OpenAI 兼容的 Embedding API

向量搜索作为语义兜底——当精确/模糊匹配都 miss 时，能捕获"那个做 AI 的朋友"这类查询（即使节点名是"张三"，summary 是"在字节做大模型"）。

## 与其他方案对比

| 特性 | Brain-Mem | 简单 RAG | Mem0 | Letta/MemGPT |
|:----|:---------:|:--------:|:----:|:------------:|
| 选择性编码 | ✅ | ❌ | ✅ | ✅ |
| 知识图谱存储 | ✅ | ❌ | ✅ | ❌ |
| 向量语义搜索 | ✅ | ✅ | ✅ | ✅ |
| 情绪共鸣 | ✅ | ❌ | ❌ | ❌ |
| 睡眠巩固 | ✅ | ❌ | ❌ | ❌ |
| 自然遗忘（衰减） | ✅ | ❌ | ❌ | ❌ |
| 记忆重巩固 | ✅ | ❌ | ❌ | ❌ |
| 前瞻性记忆 | ✅ | ❌ | ❌ | ❌ |
| 创造性重组 | ✅ | ❌ | ❌ | ❌ |
| 间隔重复 | ✅ | ❌ | ❌ | ❌ |
| 分层存储路由 | ✅ | ❌ | ❌ | ✅ |
| 自托管 / 无厂商锁定 | ✅ | ✅ | ⚠️ | ✅ |

## Roadmap

- [ ] 插件 SDK：自定义感知器/编码器规则
- [ ] 多 Agent 共享记忆 + 访问控制
- [ ] Web 可视化面板
- [ ] 基准测试（LOCOMO 等记忆评测）
- [ ] 更多 LLM 提供商的原生支持

## 贡献

欢迎贡献！请先开 Issue 讨论你想改什么。

## 许可证

[MIT](LICENSE)

---

<div align="center">

*"记忆不是过去的录像，而是现在的重构。"*
— Daniel Schacter《记忆的七宗罪》

</div>
