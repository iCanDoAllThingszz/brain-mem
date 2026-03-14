<div align="center">

# 🧠 Brain-Mem

### Brain-Inspired Memory System for AI Agents

*Give your AI agent a brain that remembers, forgets, dreams, and grows.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Neo4j](https://img.shields.io/badge/Neo4j-4.x-008CC1.svg)](https://neo4j.com)
[![OpenClaw Plugin](https://img.shields.io/badge/OpenClaw-Plugin-orange.svg)](https://github.com/openclaw/openclaw)

**English** | [中文](README_CN.md)

---

<img src="https://img.shields.io/badge/Perceiver-Thalamus-ff6b6b?style=for-the-badge" />
<img src="https://img.shields.io/badge/Evaluator-Prefrontal_Cortex-ffa502?style=for-the-badge" />
<img src="https://img.shields.io/badge/Encoder-Hippocampus-7bed9f?style=for-the-badge" />
<img src="https://img.shields.io/badge/Retriever-Multi_Path_Recall-70a1ff?style=for-the-badge" />
<img src="https://img.shields.io/badge/Consolidator-Sleep-a29bfe?style=for-the-badge" />

</div>

---

## 💡 Why Brain-Mem?

Most AI agents have amnesia. They forget what you said yesterday, can't connect dots across conversations, and treat every session as a blank slate.

Brain-Mem fixes this by giving agents a **human-like memory system** — one that:

- 🎯 **Selectively encodes** what matters (not everything)
- 😢 **Weighs emotions** in memory formation and recall
- 🌙 **Consolidates during sleep** (nightly cron) — deduplicates, discovers patterns, even dreams up creative insights
- 📉 **Naturally forgets** unimportant things over time
- 🔄 **Updates memories** when corrected ("actually, that interview went well")
- ⏰ **Remembers the future** ("remind me about X next time we talk about Y")

## 🏗️ Architecture

### The Memory Pipeline

```
                    ┌─────────────────────────────────────┐
                    │         Working Memory               │
                    │   (user profile, goals, emotions)    │
                    └──────────┬──────────────────────────┘
                               │ provides context to all
            ┌──────────────────┼──────────────────────┐
            ▼                  ▼                      ▼
     ┌────────────┐    ┌────────────┐         ┌────────────┐
     │ Perceiver  │───▶│ Evaluator  │         │ Retriever  │
     │ (Thalamus) │    │(Prefrontal)│         │(Multi-path)│
     └────────────┘    └─────┬──────┘         └─────┬──────┘
                             │                      │
                             ▼                      │
                       ┌────────────┐               │
                       │  Encoder   │               │
                       │(Hippocampus)│              │
                       └─────┬──────┘               │
                             │                      │
                             ▼                      │
                    ┌─────────────────┐             │
                    │  Encoder Buffer │◀────────────┘
                    │   (SQLite)      │  also searches buffer
                    └────────┬────────┘
                             │ nightly
                             ▼
                    ┌─────────────────┐
                    │  Consolidator   │
                    │  (Sleep cycle)  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   Neo4j Graph   │◀──── Retriever queries
                    │ (Long-term Mem) │
                    └─────────────────┘
```

### v3: Layered Storage

Not everything belongs in a knowledge graph. Brain-Mem routes information to the right place:

| What you said | Category | Where it goes |
|:---|:---|:---|
| "我决定跳槽" | `cognition` | 📊 **Graph** — entity + relations |
| "中午吃了沙拉300大卡" | `log_diet` | 📄 **File** + graph index |
| "跑了5公里" | `log_exercise` | 📄 **File** + graph index |
| "腾讯二面聊了分布式" | `log_interview` | 📄 **File** + graph index |
| "不对，面试其实很好" | `reconsolidation` | 🔄 **Graph update** (correct existing node) |
| "明天提醒我开会" | `prospective` | ⏰ **Graph** (trigger node) |
| "忘掉这个人" | `forget` | 🚫 **Graph** (suppress node) |
| "嗯嗯" | `noise` | 🗑️ Discarded |

## 🧬 8 Auxiliary Mechanisms

Beyond the core pipeline, Brain-Mem implements cognitive science mechanisms that make memory feel *alive*:

| # | Mechanism | Inspiration | What it does |
|:--|:----------|:------------|:-------------|
| 1 | 🎭 **Emotional Resonance** | Mood-congruent memory | Sad? Recall sad memories for empathy + happy ones for encouragement |
| 2 | 🔄 **Reconsolidation** | Memory updating on recall | "Actually that went well" → updates the stored memory |
| 3 | ⏰ **Prospective Memory** | Future intentions | Time triggers ("remind me tomorrow") + event triggers ("next time we discuss X") |
| 4 | 🧹 **Motivated Forgetting** | Suppression | "Forget this person" → node hidden, never retrieved |
| 5 | 📅 **Spaced Repetition** | Anki-style intervals | Important fading memories get flagged for natural review (1→3→7→21 days) |
| 6 | ⚔️ **Interference** | Proactive/retroactive | New info contradicts old? Old relation gets `valid_until`, new one created |
| 7 | 💡 **Creative Recombination** | REM sleep dreaming | Random memory fragments combined → occasional valuable insights |
| 8 | 🔍 **Retrieval Compensation** | Tip-of-tongue | Empty results? Retry with relaxed thresholds and deeper graph traversal |

## 📖 A Day in the Life

Here's how all the pieces work together in a real day:

### 🌅 9:00 AM — Session Start
```
Working Memory boots up:
├── Goals: [减肥计划, 跳槽计划]
├── Spaced repetition: "不喜欢吃香菜" needs review
└── Prospective: "9:00 提醒交报告" → TRIGGERED!
```
> 🤖 "早上好！别忘了今天要交报告"

### 🥪 9:15 AM — Diet Logging
```
"早上吃了三明治，400大卡"
  → log_diet → File: diet/2026-03-14.md
  → Retriever recalls: "目标1600大卡/天"
```
> 🤖 "记上了！还剩1200大卡"

### 😢 10:30 AM — Emotional Event
```
"腾讯二面挂了，好沮丧"
  → cognition, emotion=sadness(7/10)
  → Emotional resonance activates:
     ├── Empathy: past failures recalled
     └── Encouragement: past successes boosted
```
> 🤖 "上次XX也没过，但后来拿到了更好的offer"

### 🔄 11:00 AM — Memory Correction
```
"不对，其实面试感觉还行"
  → reconsolidation → update emotion: sadness → neutral
  → Old value saved in correction history
```

### 🥗 12:00 PM — Spaced Repetition Success
```
"推荐个晚餐"
  → Retriever finds: "不喜欢吃香菜" (flagged for review)
  → Successfully recalled! Review interval extended to 3 days
```
> 🤖 "推荐几个清淡的，都没有香菜"

### ⏰ 2:00 PM — Setting a Future Reminder
```
"下次聊到字节时提醒我问进度"
  → prospective, trigger=event("字节"), status=pending
```

### 🔔 3:00 PM — Event Trigger Fires
```
"字节那边有消息吗"
  → ProspectiveChecker: "字节" matches! → inject reminder
```
> 🤖 "对了，你之前让我提醒你问字节面试进度"

### 🚫 4:00 PM — Forgetting on Demand
```
"忘掉魏小康"
  → forget → node.status = suppressed
  → Still in graph, but invisible to retrieval
```

### 🌙 1:00 AM — Sleep Consolidation
```
Consolidator runs:
├── Deduplicate today's entities
├── Resolve conflicts
├── Discover patterns: "面试频率在加速"
├── Creative recombination: 2 attempts
│   └── Insight: "brain-memory可以做成开源产品" ✨
├── Spaced repetition: flag fading important memories
├── Global decay: all nodes age naturally
└── Archive buffer
```

## 🛠️ Tech Stack

| Component | Technology |
|:----------|:----------|
| API Server | Python 3.11 · FastAPI · Uvicorn |
| Long-term Memory | Neo4j 4.x |
| Short-term Buffer | SQLite |
| File Logs | Markdown |
| LLM Backend | Any OpenAI-compatible API |
| Plugin Host | OpenClaw Gateway (TypeScript) |
| Process Manager | systemd |

## 📁 Project Structure

```
brain-mem/
├── server/
│   ├── app.py                        # FastAPI + hook routing
│   ├── engine/
│   │   ├── perceiver.py              # 🔴 Thalamus — classify & rewrite
│   │   ├── evaluator.py              # 🟠 Prefrontal — score & decide
│   │   ├── encoder.py                # 🟢 Hippocampus — extract & encode
│   │   ├── retriever.py              # 🔵 Multi-path recall + emotional resonance
│   │   ├── consolidator.py           # 🟣 Sleep — consolidate + dream
│   │   ├── working_memory.py         # Session context cache
│   │   ├── log_writer.py             # v3 file logger + graph index
│   │   ├── prospective_checker.py    # ⏰ Time/event trigger checker
│   │   └── llm_client.py             # LLM API client
│   ├── storage/
│   │   ├── graph.py                  # Neo4j operations
│   │   ├── buffer.py                 # SQLite buffer
│   │   └── tag_dict.py              # Tag taxonomy
│   └── models/
│       ├── node.py                   # MemoryNode
│       └── relation.py               # Relation
├── docs/
│   └── V3-DESIGN.md                  # Architecture design doc
├── data/                             # Runtime data (auto-created)
└── config.yaml
```

## 🚀 Quick Start

```bash
# 1. Clone & install
git clone https://github.com/iCanDoAllThingszz/brain-mem.git
cd brain-mem
pip install -r requirements.txt

# 2. Start Neo4j
docker run -d --name neo4j-memory \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:4.4

# 3. Configure
cp config.yaml.example config.yaml
# Edit config.yaml with your Neo4j password and LLM API key

# 4. Run
python -m uvicorn server.app:app --host 0.0.0.0 --port 8100

# 5. Setup nightly consolidation
echo "30 17 * * * curl -s -X POST http://localhost:8100/hooks/consolidate \
  -H 'Content-Type: application/json' \
  -d '{\"tenant_id\":\"default\",\"user_id\":\"your-user\"}'" | crontab -
```

## 📡 API

| Method | Endpoint | Description |
|:-------|:---------|:------------|
| `GET` | `/health` | Health check |
| `GET` | `/logs?n=30` | Activity logs |
| `POST` | `/hooks/session-start` | Load working memory |
| `POST` | `/hooks/before-query` | Retrieve memories |
| `POST` | `/hooks/after-response` | Encode user message |
| `POST` | `/hooks/session-end` | Session cleanup |
| `POST` | `/hooks/consolidate` | Trigger consolidation |
| `POST` | `/hooks/check-prospective` | Check prospective triggers |

## 📉 Memory Decay Model

Inspired by the Ebbinghaus forgetting curve:

```
effective_half_life = base × (1 + importance/10) × zone_factor

Zone factors:
  🎬 episodic   = 0.5   (events fade fast)
  📚 semantic   = 2.0   (facts persist)
  🔧 procedural = 3.0   (skills last longest)
  💛 emotional  = 1.0   (baseline)

Example (base = 30 days):
  Event,  imp=5:  30 × 1.5 × 0.5 =  22 days
  Fact,   imp=5:  30 × 1.5 × 2.0 =  90 days
  Skill,  imp=8:  30 × 1.8 × 3.0 = 162 days
```

## 📄 License

MIT

---

<div align="center">

Built with 🧠 by **酪酪 & 禹哥**

*"记忆不是过去的录像，而是现在的重构。" — Daniel Schacter*

</div>
