# 🧠 Brain-Mem: Brain-Inspired Memory System for AI Agents

> *"记忆不是过去的录像，而是现在的重构。" — Daniel Schacter*

[English](#english) | [中文](#中文)

---

<a name="english"></a>

## Overview

Brain-Mem is a cognitive science-inspired memory system for AI agents. It models the human brain's memory architecture — from sensory gating (thalamus) to emotional evaluation (amygdala), hippocampal encoding, sleep consolidation, and natural forgetting with spaced repetition.

Built as an **OpenClaw plugin**, it augments (not replaces) the host agent's context with long-term memories that the conversation history alone cannot provide.

### Design Philosophy

- **Augmentation, not replacement** — The host agent already has conversation history. We only inject what it doesn't have: cross-session memories, long-term patterns, forgotten context.
- **Cognition in graph, details in files** — Knowledge graph stores high-level understanding (decisions, relationships, milestones). File system stores granular logs (diet records, exercise data, interview notes).
- **Single-message focus** — Only encode the current user message, never re-encode conversation history.
- **Emotion-driven** — Emotional intensity influences both encoding priority and retrieval ranking, just like the human brain.

## Architecture

### 7 Core Components

| Component | Brain Analog | Role |
|-----------|-------------|------|
| **Perceiver** | Thalamus + Sensory Cortex | Classify messages: noise / command / informative. Route to appropriate pipeline. |
| **Evaluator** | Prefrontal Cortex + Amygdala | Score task_relevance × emotional_intensity × novelty. Decide encode or discard. |
| **Encoder** | Hippocampus | Extract entities & relations. Resolve against existing graph. Write to buffer or file logs. |
| **Working Memory** | Prefrontal Working Memory | Session-level context: user profile, active goals, emotional baseline, pending reviews. |
| **Consolidator** | Sleep Consolidation | Nightly: deduplicate, resolve conflicts, discover patterns, creative recombination, decay. |
| **Long-term Memory** | Cerebral Cortex | Neo4j knowledge graph with 4 zones: semantic, episodic, procedural, emotional. |
| **Retriever** | Hippocampal Recall | Multi-path search + emotional resonance scoring + LLM reconstruction. |

### 4 Collaboration Pipelines

```
Pipeline A: ENCODING (async, doesn't block response)
User message → Perceiver → Evaluator → Encoder → Buffer/File + Graph Index

Pipeline B: RETRIEVAL (sync, injects into LLM context)
User query → Retriever → Multi-path search → Score & rank → LLM reconstruct → <retrieved-memories>

Pipeline C: SESSION START (sync, before first response)
New session → Load Working Memory from graph + buffer → Ready

Pipeline D: CONSOLIDATION (async, nightly cron)
Buffer → Deduplicate → Conflict resolution → Pattern discovery → Creative recombination
→ Spaced repetition check → Write to graph → Global decay → Archive buffer
```

### v3 Layered Storage

```
User says: "中午吃了沙拉300大卡"

  ┌─ Perceiver: category = log_diet, target = 减肥计划
  │
  ├─ File: memory/logs/diet/2026-03-14.md
  │    "- 12:00 赵禹午餐吃了沙拉，300大卡"
  │
  ├─ Buffer: summary index (for retriever discoverability)
  │    "[减肥计划] 赵禹午餐沙拉300大卡 (详见: memory/logs/diet/)"
  │
  └─ Graph: update 减肥计划 node → last_log_date = 2026-03-14

User says: "我决定下周开始学Rust"

  ┌─ Perceiver: category = cognition
  │
  └─ Graph: create/update entities → 赵禹 -[DECIDED_TO]-> 学习Rust
```

**Category routing:**

| Category | Storage | Evaluator | Example |
|----------|---------|-----------|---------|
| `cognition` | Graph (entities + relations) | Full evaluation | "我决定跳槽" |
| `log_diet` | File + buffer index + graph index | Auto-pass | "吃了苹果" |
| `log_exercise` | File + buffer index + graph index | Auto-pass | "跑了5公里" |
| `log_interview` | File + buffer index + graph index | Auto-pass | "腾讯二面聊了分布式" |
| `log_trading` | File + buffer index + graph index | Auto-pass | "买了0.1个BTC" |
| `log_learning` | File + buffer index + graph index | Auto-pass | "学了Rust所有权" |
| `reconsolidation` | Graph (update existing node) | Auto-pass | "不对，面试其实很好" |
| `prospective` | Graph (trigger node) | Auto-pass | "明天提醒我开会" |
| `forget` | Graph (suppress node) | Auto-pass | "忘掉这件事" |

## Auxiliary Memory Mechanisms

Beyond the 7 core components, Brain-Mem implements 8 auxiliary mechanisms inspired by cognitive science:

### 🎭 Emotional Resonance Retrieval
Current emotional state influences memory recall. When the user is sad, negative memories surface for empathy, but positive memories also get a boost for encouragement.

### 🔄 Memory Reconsolidation
When users correct or supplement past memories ("不对，面试其实很好"), the system updates the corresponding graph node — just like how human memories are modified each time they're recalled.

### ⏰ Prospective Memory
"明天提醒我交报告" creates a time-triggered reminder node. "下次聊到面试时问问结果" creates an event-triggered node. Triggers are checked at session start and during each query.

### 🧹 Motivated Forgetting
"忘掉这个人" marks the node as `suppressed` — it stays in the graph but never appears in retrieval results. Memories aren't deleted, just hidden (like the human brain).

### 📅 Spaced Repetition
Important memories approaching decay threshold are flagged for review. Anki-style intervals: 1 → 3 → 7 → 21 days, then doubling. Successfully recalled memories get their review interval extended.

### ⚔️ Interference Forgetting
When new information contradicts old information, old relations are marked with `valid_until` and new ones created. Conflicts are flagged for the consolidator to resolve.

### 💡 Creative Recombination
During nightly consolidation, random memory fragments are combined and fed to an LLM to discover unexpected connections — mimicking REM sleep creativity. Most attempts yield nothing; occasionally, a valuable insight emerges.

### 🔍 Retrieval Failure Compensation
When initial retrieval returns empty, the system retries with relaxed thresholds and expanded graph traversal depth — mimicking the "tip of the tongue" phenomenon where you try different recall paths.

## A Day in the Life: Complete Workflow Example

**9:00 AM — New Session Starts (Pipeline C)**
```
Working Memory loads from graph:
├── User profile: 赵禹, 29, developer at Meituan
├── Active goals: [减肥计划, 跳槽计划]
├── Emotional baseline: neutral
├── Spaced repetition: "不喜欢吃香菜" flagged for review
└── Prospective memory: "9:00 提醒交报告" triggered!
```
→ Agent: "早上好！别忘了今天要交报告哦"

**9:15 AM — Diet Log**
```
"早上吃了三明治，400大卡"
→ Perceiver: log_diet, target=减肥计划
→ File: memory/logs/diet/2026-03-14.md ← "09:15 三明治 400大卡"
→ Graph: 减肥计划.last_log_date = 2026-03-14
→ Retriever recalls: "目标每日1600大卡"
```
→ Agent: "记上了！还剩1200大卡额度"

**10:30 AM — Emotional Event**
```
"腾讯二面挂了，好沮丧"
→ Perceiver: cognition (milestone)
→ Evaluator: relevance=9, emotion=7(sadness), novelty=8 → HIGH priority
→ Encoder: create 腾讯二面 node, emotion=sadness
→ Retriever (emotional resonance active):
   ├── Empathy: recalls past interview failures (mood-congruent)
   └── Encouragement: recalls past successes (positive boost)
```
→ Agent: "上次XX也没过，但后来拿到了更好的offer"

**11:00 AM — Memory Reconsolidation**
```
"不对，其实腾讯二面感觉还行"
→ Perceiver: reconsolidation, correction_type=reframe
→ Encoder: locate 腾讯二面 node → update emotion: sadness→neutral
→ version += 1, old value saved in _correction_history
```

**12:00 PM — Retrieval with Spaced Repetition**
```
"推荐个晚餐，少吃点"
→ Retriever recalls:
   ├── Today's intake: 400+800 = 1200大卡
   ├── "不喜欢吃香菜" (spaced repetition — successfully recalled!)
   │   └── Clear needs_review flag, schedule next review in 3 days
   └── Goal: 1600大卡/day
```
→ Agent: "还剩400大卡。推荐几个清淡的，都没有香菜"

**2:00 PM — Prospective Memory (Event Trigger)**
```
"下次聊到字节时提醒我问进度"
→ Perceiver: prospective, trigger_type=event, trigger_value="字节"
→ Encoder: create trigger node in graph (status=pending)
```

**3:00 PM — Event Trigger Fires**
```
"字节那边有消息吗"
→ ProspectiveChecker: "字节" matches event trigger!
→ Inject reminder into context
→ Trigger status → completed
```
→ Agent: "对了，你之前让我提醒你问字节面试进度"

**4:00 PM — Motivated Forgetting**
```
"忘掉魏小康这个人"
→ Perceiver: forget, target=魏小康
→ Encoder: node.status = suppressed, retrieval_strength = 0
→ Node stays in graph but never appears in search results
```

**1:00 AM — Sleep Consolidation (Pipeline D)**
```
Consolidator runs:
├── Replay & filter: discard low-importance buffer entries
├── Deduplicate: merge same-day duplicate entities
├── Conflict resolution: resolve _conflict_with flagged nodes
├── Pattern discovery: "面试频率在加速" → create insight
├── Creative recombination: random node combination
│   → "AI Agent学习 + 记忆系统项目 + 副业探索"
│   → Insight: "brain-memory可以做成开源产品" (confidence=0.5)
├── Spaced repetition: flag decaying important memories
├── Write to graph: finalize all changes
├── Global decay: all nodes age
└── Archive buffer
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API Server | Python 3.11 + FastAPI + Uvicorn |
| Long-term Memory | Neo4j 4.x Graph Database |
| Short-term Buffer | SQLite |
| File Logs | Markdown (human-readable) |
| LLM Backend | OpenAI-compatible API |
| Plugin Host | OpenClaw Gateway (TypeScript) |
| Process Manager | systemd |

## Project Structure

```
brain-mem/
├── server/
│   ├── app.py                        # FastAPI endpoints + hook routing
│   ├── engine/
│   │   ├── perceiver.py              # Classification + rewrite (thalamus)
│   │   ├── evaluator.py              # Multi-dimensional scoring (prefrontal)
│   │   ├── encoder.py                # Entity extraction + resolution (hippocampus)
│   │   ├── retriever.py              # Multi-path retrieval + emotional resonance
│   │   ├── consolidator.py           # Sleep consolidation + creative recombination
│   │   ├── working_memory.py         # Session context + spaced repetition
│   │   ├── log_writer.py             # v3 file log writer + graph index
│   │   ├── prospective_checker.py    # Time/event trigger checker
│   │   └── llm_client.py             # LLM API client
│   ├── storage/
│   │   ├── graph.py                  # Neo4j async operations
│   │   ├── buffer.py                 # SQLite encoder buffer
│   │   └── tag_dict.py               # Tag taxonomy
│   └── models/
│       ├── node.py                   # MemoryNode model
│       └── relation.py               # Relation model
├── docs/
│   └── V3-DESIGN.md                  # v3 layered storage design
├── data/                             # Auto-created runtime data
├── config.yaml                       # Configuration
└── requirements.txt
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/logs?n=30` | Activity logs |
| POST | `/hooks/session-start` | Load working memory |
| POST | `/hooks/before-query` | Retrieve memories for query |
| POST | `/hooks/after-response` | Encode user message |
| POST | `/hooks/session-end` | Session cleanup |
| POST | `/hooks/consolidate` | Trigger consolidation |
| POST | `/hooks/check-prospective` | Check prospective memory triggers |

## Quick Start

### Prerequisites
- Python 3.11+, Neo4j 4.x+ (Docker recommended), OpenAI-compatible LLM API

### Setup
```bash
# 1. Install
pip install -r requirements.txt

# 2. Start Neo4j
docker run -d --name neo4j-memory \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:4.4

# 3. Configure config.yaml (see config.yaml.example)

# 4. Run
python -m uvicorn server.app:app --host 0.0.0.0 --port 8100

# 5. Setup nightly consolidation cron
30 17 * * * curl -s -X POST http://localhost:8100/hooks/consolidate \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"default","user_id":"your-user"}'
```

## Memory Decay Model

Based on the Ebbinghaus forgetting curve with biological enhancements:

```
effective_half_life = base_half_life × (1 + importance/10) × zone_factor

zone_factor:
  episodic  = 0.5  (events fade fast)
  semantic  = 2.0  (facts persist)
  procedural = 3.0 (skills last longest)
  emotional = 1.0  (baseline)

Example (base = 30 days):
  episodic,  importance=5:  30 × 1.5 × 0.5 = 22.5 days
  semantic,  importance=5:  30 × 1.5 × 2.0 = 90 days
  procedural, importance=8: 30 × 1.8 × 3.0 = 162 days
```

## License

MIT

---

*Built with 🧠 by 酪酪 & 禹哥*
