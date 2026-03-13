# 🧠 Brain-Mem: Brain-Inspired Memory System for AI Agents

[English](#english) | [中文](#中文)

---

<a name="english"></a>

## Overview

Brain-Mem is a brain-inspired memory system designed for AI agents. It mimics the human brain's memory architecture — from sensory gating (thalamus) to short-term encoding (hippocampus) to long-term consolidation (sleep) and natural forgetting (memory decay).

Built as an **OpenClaw plugin**, it provides AI agents with persistent, structured, and evolving memory that goes far beyond simple conversation history.

## Architecture

```
User Message
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Perceiver (Thalamus / Sensory Cortex)              │
│  Rapid classification: noise / command / informative │
└──────────────────────┬──────────────────────────────┘
                       │ informative
                       ▼
┌─────────────────────────────────────────────────────┐
│  Evaluator (Prefrontal Cortex / Amygdala)           │
│  Multi-dimensional scoring:                          │
│    task_relevance × emotional_intensity × novelty    │
│  Decision: encode or discard                         │
└──────────────────────┬──────────────────────────────┘
                       │ encode=true
                       ▼
┌─────────────────────────────────────────────────────┐
│  Encoder (Hippocampus)                               │
│  1. Coarse extraction: entities + relations          │
│  2. Tag resolution: multi-level tag taxonomy         │
│  3. Entity resolution: search same-tag entities      │
│     in graph → LLM decides create/merge/update       │
│  4. Dedup check → write to buffer                    │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Encoder Buffer (Hippocampal Buffer)                 │
│  SQLite short-term storage                           │
│  Awaiting consolidation into long-term graph         │
└──────────────────────┬──────────────────────────────┘
                       │ daily consolidation (cron)
                       ▼
┌─────────────────────────────────────────────────────┐
│  Consolidator (Sleep Consolidation)                  │
│  1. Upsert entities (create/merge/update)            │
│  2. Create relations                                 │
│  3. Pattern discovery (cross-event analysis)         │
│  4. Memory decay (importance-weighted, zone-based)   │
│  5. Per-unit archive                                 │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Neo4j Knowledge Graph (Long-Term Memory)            │
│  Nodes: semantic / episodic / procedural / emotional │
│  Relations: typed, timestamped, session-tracked      │
│  Decay: zone-differentiated half-lives               │
│  Revival: dormant nodes can be reactivated           │
└─────────────────────────────────────────────────────┘
```

### Retrieval Flow

```
Query arrives
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Working Memory (Prefrontal Cortex)                  │
│  Cold-boot from graph: user profile, active goals,   │
│  recent events, emotional baseline, last session     │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  Retriever (Multi-Path Recall)                       │
│  Path A: Exact name match                            │
│  Path B: Alias match                                 │
│  Path C: Fuzzy keyword match                         │
│  Path D: Dormant node search (for revival)           │
│  + Relation traversal (1-2 hops)                     │
│  + Buffer retrieval (recent unarchived)              │
│  → Score: relevance×0.4 + importance×0.2             │
│           + recency×0.2 + access_freq×0.1            │
│           + emotional×0.1                            │
│  → LLM reconstructs top-K into coherent context      │
│  → Retrieval strengthens memory (+0.5 strength)      │
│  → Dormant nodes revived if retrieved                │
└─────────────────────────────────────────────────────┘
```

## Key Features

### 🧬 Entity Lifecycle Management
- **Tag taxonomy**: 15 core tags + LLM-driven semantic similarity matching
- **Entity resolution**: Before creating a new entity, searches graph for same-tag entities and lets LLM decide: create / merge / update
- **Alias management**: "赵禹" and "禹哥" are the same person — aliases, not duplicates
- **Buffer dedup**: Same message won't be encoded twice

### 🌙 Sleep Consolidation
- **Per-unit archive**: Failed units are retried next cycle, not lost
- **Pattern discovery**: LLM analyzes memory fragments for recurring themes and conflicts
- **Tag merging**: New tags are merged into existing nodes, not overwritten

### 🧊 Forgetting & Revival
- **Importance-weighted decay**: High-importance memories decay slower (effective half-life = base × (1 + importance/10))
- **Zone-differentiated decay**:
  - Episodic (events): fast decay (×0.5)
  - Semantic (facts): slow decay (×2.0)
  - Procedural (skills): slowest decay (×3.0)
- **Retrieval strengthening**: Each recall adds +0.5 to retrieval_strength (cap 10)
- **Dormant revival**: Forgotten memories can be reactivated when relevant queries match them

### 📊 Activity Logging
- Structured JSON logs for every pipeline stage
- Rolling 500-entry log file
- HTTP endpoint: `GET /logs?n=30`
- CLI: `openclaw brain logs`

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API Server | Python + FastAPI + Uvicorn |
| Long-term Memory | Neo4j Graph Database |
| Short-term Buffer | SQLite |
| LLM Backend | OpenAI-compatible API (MiniMax-M2.5) |
| Plugin Host | OpenClaw Gateway (TypeScript) |
| Process Manager | systemd |

## Project Structure

```
brain-mem/
├── server/
│   ├── app.py                    # FastAPI application + endpoints
│   ├── activity_log.py           # Structured activity logging
│   ├── engine/
│   │   ├── perceiver.py          # Message classification (thalamus)
│   │   ├── evaluator.py          # Memory value scoring (prefrontal cortex)
│   │   ├── encoder.py            # Entity extraction + resolution (hippocampus)
│   │   ├── retriever.py          # Multi-path retrieval + reconstruction
│   │   ├── consolidator.py       # Sleep consolidation (buffer → graph)
│   │   ├── working_memory.py     # Session-level context cache
│   │   └── llm_client.py         # LLM API client
│   ├── storage/
│   │   ├── graph.py              # Neo4j async operations
│   │   ├── buffer.py             # SQLite encoder buffer
│   │   └── tag_dict.py           # Multi-level tag taxonomy
│   └── models/
│       ├── node.py               # MemoryNode data model
│       └── relation.py           # Relation data model
├── data/
│   ├── buffer.db                 # SQLite buffer (auto-created)
│   ├── tag_dict.json             # Tag taxonomy (auto-created)
│   └── activity.log              # Activity logs (auto-created)
├── config.yaml                   # Server + Neo4j + LLM configuration
├── scripts/
│   └── cleanup.py                # One-time data cleanup utility
└── requirements.txt
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/logs?n=30` | View recent activity logs |
| POST | `/hooks/session-start` | Load working memory for a session |
| POST | `/hooks/before-query` | Retrieve relevant memories for a query |
| POST | `/hooks/after-response` | Encode user message into buffer |
| POST | `/hooks/session-end` | Generate session summary |
| POST | `/hooks/consolidate` | Trigger sleep consolidation |

## Integration with OpenClaw

Brain-Mem integrates with OpenClaw as a **plugin** via lifecycle hooks:

### Plugin Location
```
~/.openclaw/extensions/brain-memory/
├── package.json
├── openclaw.plugin.json
└── index.ts
```

### Lifecycle Hooks

| Hook | Trigger | Action |
|------|---------|--------|
| `before_agent_start` | Every incoming message | Inject `<working-memory>` + `<retrieved-memories>` into LLM context |
| `agent_end` | After LLM response | Encode user messages through perceiver → evaluator → encoder pipeline |
| `session_end` | Session close | Generate session summary |

### Registered Tools

| Tool | Description |
|------|-------------|
| `brain_recall` | Manually search long-term memory graph |
| `brain_consolidate` | Manually trigger sleep consolidation |

### CLI Commands

```bash
openclaw brain health        # Check server health
openclaw brain recall <query> # Search memory
openclaw brain consolidate   # Trigger consolidation
openclaw brain logs -n 20    # View activity logs
openclaw brain start         # Start server
openclaw brain stop          # Stop server
```

### Plugin Configuration

In OpenClaw config:
```yaml
plugins:
  brain-memory:
    serverUrl: "http://localhost:8100"
    tenantId: "default"
    userId: "yugo"
    autoStart: true
    serverPath: "/path/to/brain-mem"
```

## Quick Start

### Prerequisites
- Python 3.11+
- Neo4j 4.x+ (Docker recommended)
- OpenAI-compatible LLM API

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure
```yaml
# config.yaml
server:
  host: "0.0.0.0"
  port: 8100

storage:
  neo4j:
    uri: "bolt://localhost:7687"
    user: "neo4j"
    password: "your-password"
  buffer:
    path: "./data/buffer.db"
  tag_dict:
    path: "./data/tag_dict.json"

llm:
  base_url: "https://api.openai.com/v1"
  model: "gpt-4o-mini"
  api_key: ""
  temperature: 0.3
```

### 3. Start Neo4j
```bash
docker run -d --name neo4j-memory \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:4.4
```

### 4. Run Server
```bash
python -m uvicorn server.app:app --host 0.0.0.0 --port 8100
```

### 5. (Optional) systemd Service
```ini
[Unit]
Description=Brain Memory Server
After=network.target docker.service

[Service]
Type=simple
WorkingDirectory=/path/to/brain-mem
ExecStart=/usr/bin/python3 -m uvicorn server.app:app --host 0.0.0.0 --port 8100
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 6. Setup Consolidation Cron
```bash
# Daily consolidation at 01:30 (adjust timezone)
30 17 * * * curl -s -X POST http://localhost:8100/hooks/consolidate \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"default","user_id":"yugo"}'
```

## Memory Decay Model

The decay model is inspired by the Ebbinghaus forgetting curve with biological enhancements:

```
effective_half_life = base_half_life × (1 + importance/10) × zone_factor

zone_factor:
  episodic  = 0.5  (events fade fast)
  semantic  = 2.0  (facts persist)
  procedural = 3.0 (skills last longest)
  emotional = 1.0  (baseline)

new_strength = strength × decay_factor × e^(-ln2 / effective_half_life × days_since_access)

If strength < 0.1 → status = 'dormant'
If dormant node is retrieved → revive (strength = 5.0, status = 'active')
Each retrieval → strength += 0.5 (cap 10.0)
```

## License

MIT

---

<a name="中文"></a>

## 概述

Brain-Mem 是一个面向 AI Agent 的类脑记忆系统。它模拟人脑的记忆架构——从感觉门控（丘脑）到短期编码（海马体）到长期巩固（睡眠）再到自然遗忘（记忆衰减）。

作为 **OpenClaw 插件**运行，为 AI Agent 提供持久化、结构化、可进化的记忆能力，远超简单的对话历史。

## 核心架构

### 编码流程（信息输入）

```
用户消息
    │
    ▼
感知器 (Perceiver) — 丘脑/感觉皮层
    │ 快速分类: noise / command / informative
    ▼
评估器 (Evaluator) — 前额叶/杏仁核
    │ 多维评分: 任务相关性 × 情感强度 × 新颖度
    │ 决策: 编码 or 丢弃
    ▼
编码器 (Encoder) — 海马体
    │ 1. 粗提取: 实体 + 关系
    │ 2. Tag归属: 多级标签体系 + LLM语义匹配
    │ 3. 实体解析: 按tag检索同类实体 → LLM判断 create/merge/update
    │ 4. 去重检查 → 写入缓冲区
    ▼
编码缓冲区 (Buffer) — 海马体缓冲区
    │ SQLite短期存储，等待巩固
    ▼ 每日凌晨定时巩固
巩固器 (Consolidator) — 睡眠巩固
    │ 1. 实体写入图谱 (create/merge/update)
    │ 2. 创建关系
    │ 3. 模式发现 (跨事件分析)
    │ 4. 记忆衰减 (importance加权 + zone差异化)
    │ 5. 逐条归档
    ▼
Neo4j 知识图谱 — 长期记忆
```

### 检索流程（信息输出）

```
查询到达
    │
    ▼
工作记忆 (Working Memory) — 前额叶工作台
    │ 冷启动加载: 用户画像、活跃目标、近期事件、情绪基线
    ▼
检索器 (Retriever) — 多路召回
    │ 路径A: 精确名称匹配
    │ 路径B: 别名匹配
    │ 路径C: 模糊关键词匹配
    │ 路径D: 休眠节点搜索（用于复活）
    │ + 关系遍历 (1-2跳)
    │ + 缓冲区检索
    │ → 综合评分 → LLM重构为连贯上下文
    │ → 检索强化记忆 (+0.5 strength)
    │ → 休眠节点被检索时自动复活
    ▼
注入到 LLM 上下文
```

## 核心特性

### 🧬 实体生命周期管理
- **多级标签体系**: 15个核心tag + LLM语义相似度匹配
- **实体解析**: 新建实体前先搜图谱同类实体，由LLM判断 create/merge/update
- **别名管理**: "赵禹"和"禹哥"是同一个人——别名，不是重复节点
- **缓冲区去重**: 同一条消息不会被编码两次

### 🌙 睡眠巩固
- **逐条归档**: 失败的unit下次重试，不会丢失
- **模式发现**: LLM分析记忆片段中的重复主题和矛盾
- **标签合并**: 新tag合并到已有节点，不覆盖

### 🧊 遗忘与复活
- **重要性加权衰减**: 高importance记忆衰减更慢
- **Zone差异化衰减**: episodic快忘(×0.5)，semantic慢忘(×2.0)，procedural最慢(×3.0)
- **检索强化**: 每次召回 +0.5 retrieval_strength
- **休眠复活**: 被遗忘的记忆在被相关查询命中时自动唤醒

### 📊 活动日志
- 每个流水线阶段的结构化JSON日志
- 滚动保留最近500条
- HTTP接口: `GET /logs?n=30`
- CLI: `openclaw brain logs`

## 遗忘模型

基于艾宾浩斯遗忘曲线，增加了生物学增强：

```
有效半衰期 = 基础半衰期 × (1 + importance/10) × zone系数

zone系数:
  episodic(事件)  = 0.5  (事件容易忘)
  semantic(知识)  = 2.0  (知识持久)
  procedural(技能) = 3.0 (技能最持久)
  emotional(情感) = 1.0  (基线)

示例 (基础半衰期=30天):
  episodic, importance=5:  半衰期 = 30 × 1.5 × 0.5 = 22.5天
  semantic, importance=5:  半衰期 = 30 × 1.5 × 2.0 = 90天
  procedural, importance=8: 半衰期 = 30 × 1.8 × 3.0 = 162天

strength < 0.1 → 进入休眠(dormant)
休眠节点被检索命中 → 复活(strength=5.0, status=active)
每次被检索 → strength += 0.5 (上限10.0)
```

## 集成 OpenClaw

Brain-Mem 通过 OpenClaw 插件机制集成，详见英文部分的 [Integration with OpenClaw](#integration-with-openclaw)。

## 快速开始

详见英文部分的 [Quick Start](#quick-start)。

## 许可证

MIT
