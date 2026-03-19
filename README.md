<p align="center">
  <h1 align="center">🧠 Brain-Mem</h1>
  <p align="center"><strong>A Cognitive Science-Inspired Memory System for AI Agents</strong></p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/Neo4j-5.x-008CC1.svg" alt="Neo4j">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-009688.svg" alt="FastAPI">
</p>

<p align="center">
  <strong>English</strong> | <a href="README_CN.md">中文</a>
</p>

---

Brain-Mem models how the **human brain** processes, stores, consolidates, and retrieves memories — implemented as a modular memory service for AI agents. Unlike simple key-value memory stores, Brain-Mem faithfully maps cognitive science mechanisms (selective encoding, sleep consolidation, natural forgetting, emotional resonance, prospective memory) into a production-grade system.

## Why Brain-Mem?

Most AI agent memory systems treat memory as a flat database: store everything, retrieve by similarity. The human brain works fundamentally differently:

- **Not everything gets stored** — the brain actively filters and evaluates incoming information
- **Memories consolidate during sleep** — important memories strengthen, trivial ones fade
- **Retrieval is multi-path** — you recall things by name, by association, by emotion, by context
- **Forgetting is a feature** — it prevents information overload and keeps memory relevant
- **Future intentions persist** — "remind me to do X when Y happens" is a real memory type
- **Cross-session continuity** — session summaries bridge conversations, so the agent never starts from scratch

Brain-Mem implements all of these mechanisms.

## Architecture: Brain ↔ System Mapping

```
                    ┌─────────────────────────────────────────────┐
                    │              Incoming Message                │
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  👁️ Perceiver (Sensory Cortex + Thalamus)   │
                    │  Filters noise, classifies, rewrites        │
                    │  Routes: cognition → graph | logs → files   │
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  🧪 Evaluator (Prefrontal Cortex + Amygdala)│
                    │  Scores importance, novelty, emotion        │
                    │  Gates what enters long-term memory         │
                    └──────────────────┬──────────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────────┐
                    │  🏗️ Encoder (Hippocampus)                   │
                    │  Entity resolution: create / merge / update │
                    │  Name mapping, relation name alignment      │
                    │  Hierarchical tag assignment                │
                    └──────┬───────────────────────┬──────────────┘
                           │                       │
              ┌────────────▼─────────┐  ┌─────────▼──────────────┐
              │  📦 Buffer (SQLite)  │  │  📝 File Logs          │
              │  Encoded memory      │  │  diet/exercise/trading  │
              │  units + embeddings  │  │  interview/learning     │
              │  Session summaries   │  │  Detailed daily records │
              └────────────┬─────────┘  └─────────┬──────────────┘
                           │                       │
              ┌────────────▼───────────────────────▼──────────────┐
              │  💤 Consolidator (Sleep Consolidation)            │
              │  Buffer → Graph: conflict resolution, merging     │
              │  Spaced repetition, creative recombination        │
              │  Graph hygiene, interference forgetting           │
              └───────────────────────────────────────────────────┘

              ┌───────────────────────────────────────────────────┐
              │  📊 Knowledge Graph (Neo4j + Vector)              │
              │  Goals, decisions, relationships, entities        │
              │  Hierarchical tags for sub-graph filtering        │
              └───────────────────────────────────────────────────┘

              ┌───────────────────────────────────────────────────┐
              │  🔍 Retriever (Multi-Path Recall)                 │
              │  5 strategies: exact → alias → fuzzy → dormant    │
              │  → vector semantic | Emotional resonance          │
              └───────────────────────────────────────────────────┘

              ┌───────────────────────────────────────────────────┐
              │  🎯 Working Memory (Session Context)              │
              │  Active goals, reminders, emotional baseline      │
              │  User profile, pending reviews (spaced rep)       │
              └───────────────────────────────────────────────────┘

              ┌───────────────────────────────────────────────────┐
              │  ⏰ Prospective Checker (Future Memory)           │
              │  Time-based & event-based triggers                │
              └───────────────────────────────────────────────────┘
```

## Component Details

| Brain Region | Component | File | Function |
|---|---|---|---|
| Sensory Cortex + Thalamus | **Perceiver** | `perceiver.py` | Filters noise (greetings, commands), classifies information into cognition vs logs, rewrites raw messages into structured form with category routing |
| Prefrontal Cortex + Amygdala | **Evaluator** | `evaluator.py` | Deep evaluation of memory worthiness. Scores importance, novelty, emotional significance. Log-type messages auto-pass (diet, exercise, etc.) |
| Hippocampus | **Encoder** | `encoder.py` | LLM-driven entity lifecycle management. Resolves pronouns, deduplicates via hierarchical tag grouping, makes create/merge/update decisions. Builds name-mapped relations. Generates session summaries from encoded data |
| Short-term Buffer | **Buffer** | `buffer.py` | SQLite-based storage for encoded memory units and session summaries. Type-filtered reads separate detail records from summaries |
| Sleep Consolidation | **Consolidator** | `consolidator.py` | Batch process: reads unarchived buffer units, resolves conflicts, writes to graph. Spaced repetition scheduling, creative recombination, LLM-driven graph hygiene |
| Memory Retrieval | **Retriever** | `retriever.py` | 5-path retrieval with emotional resonance weighting and failure compensation. Synthesizes retrieved fragments into factual context |
| Working Memory | **Working Memory** | `working_memory.py` | Per-session context cache: active goals, pending reminders/reviews, emotional baseline, user profile. Single-scan loading with deep-merge updates |
| Prospective Memory | **Prospective Checker** | `prospective_checker.py` | Future-oriented memory: time-based triggers ("remind at 3pm") and event-based triggers ("remind when X happens") |
| Embedding System | **Embedding Client** | `embedding_client.py` | Async embedding generation with LRU cache (1000 entries). Powers vector semantic search |
| Log System | **Log Writer** | `log_writer.py` | Writes detailed logs to categorized files (diet, exercise, interview, trading, learning) while maintaining graph index pointers |
| Tag Taxonomy | **Tag Dict** | `tag_dict.py` | Hierarchical tag system with parent/child relationships. LLM-assisted tag placement for new concepts |
| User Profile | **Profile Store** | `user_profile.py` | Persistent user profile with LLM-enriched goals, preferences, and traits. Incrementally updated across sessions |

## Key Features

### 1. Layered Storage (v3 Architecture)

The brain doesn't store a grocery list the same way it stores a life decision. Neither does Brain-Mem.

- **Knowledge Graph (Neo4j)** — High-level cognition: goals, decisions, relationships, milestones, insights
- **File System** — Detailed logs: diet records, exercise logs, interview notes, trading records, learning journals
- **Graph ↔ File linking** — Graph nodes point to log files via `log_path`, enabling drill-down from cognition to detail
- **Result**: The graph stays clean and meaningful. No "apple" or "beef noodle" entities polluting your knowledge graph.

```
User: "I had an apple for breakfast"

❌ Without layered storage:
   → Creates entities: Apple, User, BreakfastFruitHabit
   → Graph polluted with food items

✅ With layered storage:
   → Appends to memory/logs/diet/2026-03-14.md: "- Breakfast: apple"
   → Updates graph: DietPlan.last_diet_log = "2026-03-14"
   → Graph stays clean, detail preserved in files
```

### 2. Intelligent Encoding with Entity Name Resolution

The encoder doesn't blindly create new nodes. It follows a rigorous lifecycle:

1. **Hierarchical tag assignment** — Classify the entity using the two-level tag tree (e.g. `人物 > 同事`)
2. **Same-type retrieval** — Search existing nodes with matching tags (graph + recent buffer)
3. **LLM resolution** — One LLM call decides: `create` (new entity), `merge` (combine with existing), or `update` (modify existing)
4. **Name mapping** — Build an `original_name → final_name` mapping from all resolution results
5. **Relation alignment** — Apply the name mapping to all extracted relations, ensuring `from_name`/`to_name` match actual graph node names
6. **Embedding generation** — Auto-generates vector embedding on encode

This means if a user says "凡哥是我同事" and "凡哥" resolves to the existing node "刘凡", the relation `from_name` is corrected to "刘凡" before storage — no orphaned references.

### 3. Hierarchical Tag System

Tags are organized in a parent-child hierarchy, enabling sub-graph filtering:

```
人物 ─┬─ 家人
      ├─ 同事
      ├─ 朋友
      ├─ 同学
      └─ 客户
技术 ─┬─ 前端
      ├─ 后端
      ├─ AI/ML
      ├─ 基础设施
      └─ 数据
计划 ─┬─ 短期
      ├─ 长期
      └─ 提醒
健康 ─┬─ 运动
      ├─ 饮食
      ├─ 睡眠
      └─ 心理
财务 ─┬─ 收入
      ├─ 支出
      └─ 投资
```

- Query by parent tag (e.g. `人物`) automatically expands to include all child tags
- LLM decides whether new tags should be placed under an existing parent or created as top-level
- Prevents tag proliferation while maintaining semantic precision

### 4. Multi-Path Retrieval (5 Strategies)

Human memory retrieval isn't a single mechanism. Brain-Mem implements 5 retrieval paths:

| Path | Strategy | When It Helps |
|---|---|---|
| A | **Exact name match** | Direct entity lookup |
| B | **Alias match** | "that AI project" → matches alias of a named project |
| C | **Fuzzy keyword search** | Partial matches, related terms |
| D | **Dormant reactivation** | Resurfaces nodes not accessed recently |
| E | **Vector semantic search** | Meaning-based retrieval via embeddings |

Additional mechanisms:
- **Emotional resonance** — Non-neutral emotions dynamically shift scoring weights
- **Retrieval failure compensation** — If initial search returns too few results, auto-expands to 3-hop graph traversal

### 5. Session Summaries (Cross-Session Bridge)

At session end, the encoder generates a structured summary from **already-encoded buffer data** (not raw conversation text). This means the summary leverages the full encoding pipeline — entity resolution, importance scoring, emotional tagging — rather than re-processing raw messages.

- Summary is stored in the buffer with `type="session_summary"`
- On next session start, Working Memory loads the latest summary to provide continuity
- Buffer reads (`read_recent`, `read_unarchived`) automatically exclude summaries via SQL-level type filtering, so detail records and summaries never mix

### 6. Cognitive Science Features

Each maps to a real cognitive mechanism with a concrete implementation:

| Mechanism | Brain Basis | Implementation |
|---|---|---|
| **Spaced Repetition** | Ebbinghaus forgetting curve | Review intervals: 1→3→7→21 days, then doubling. Consolidator schedules next review |
| **Creative Recombination** | Sleep-phase insight generation | During consolidation, LLM discovers non-obvious connections between memories |
| **Memory Reconsolidation** | Memory updating on recall | User corrections auto-update existing memories without evaluation gate |
| **Interference Forgetting** | Competing memory traces | Similar memories naturally compete; weaker traces decay faster |
| **Natural Decay** | Time-based forgetting | Unused memories gradually lose retrieval strength via `decay_factor` |
| **Emotional Resonance** | Amygdala modulation | Emotionally tagged memories get retrieval priority with dynamic weight shifting |
| **Prospective Memory** | Future intention encoding | Time-based and event-based triggers, written directly to graph |
| **Motivated Forgetting** | Suppression mechanism | Nodes can be suppressed (hidden, never deleted) — recoverable but out of active retrieval |

### 7. Working Memory (Optimized)

Each conversation session gets its own working memory context, loaded in a single optimized scan:

- **Active goals** — From persistent user profile (LLM-enriched with progress tracking) or graph
- **Pending reminders** — Prospective memory triggers waiting to fire
- **Pending reviews** — Spaced repetition items due for review
- **Emotional baseline** — Computed from recent events for resonance scoring
- **Last session summary** — Cross-session continuity bridge
- **User profile** — Persistent traits, preferences, and context

Performance: single `find_active_nodes` call with in-memory filtering (previously 3 separate full scans). Deep-merge update logic preserves nested `raw` fields during incremental updates.

### 8. Vector Search

Built on Neo4j 5.x native vector index — no separate vector database needed:

- **Graph nodes**: Cosine similarity search on 1536-dimensional embeddings
- **Buffer records**: Numpy brute-force cosine (optimal for <1000 items, no ANN overhead)
- **Auto-generation**: Embeddings created on encode; backfill endpoint for existing nodes

## Storage Architecture

```
Neo4j (Knowledge Graph)           SQLite (Buffer)               File System (Logs)
┌──────────────────────┐    ┌───────────────────────┐    ┌──────────────────────────┐
│ MemoryNode            │    │ memory_buffer          │    │ memory/logs/             │
│ ├─ id, name, summary │    │ ├─ id, type, data     │    │ ├── diet/YYYY-MM-DD.md   │
│ ├─ zone, importance  │    │ ├─ importance, archived│    │ ├── exercise/...          │
│ ├─ tags[], aliases[] │    │ ├─ embedding (BLOB)   │    │ ├── interview/...         │
│ ├─ embedding[1536]   │    │ ├─ timestamp, date     │    │ ├── trading/...           │
│ ├─ emotional_tag     │    │ └─ tenant_id, user_id  │    │ ├── learning/...          │
│ ├─ decay_factor      │    │                         │    │ └── general/...           │
│ ├─ retrieval_strength│    │ Types:                  │    └──────────────────────────┘
│ ├─ confidence        │    │ - "memory" (encoded)    │
│ ├─ access_count      │    │ - "session_summary"     │
│ └─ status            │    └───────────────────────┘
└──────────────────────┘
```

**Memory Zones:**
- `episodic` — Personal events and experiences
- `semantic` — Facts, concepts, knowledge
- `procedural` — Skills, habits, how-to knowledge

## Data Flow: End-to-End Encoding Pipeline

```
User message + AI response
        │
        ▼
   Perceiver ──→ classify (cognition / log / noise)
        │              │
        │ (cognition)  │ (log)
        ▼              ▼
   Evaluator      LogWriter ──→ files
        │
        ▼ (passes importance gate)
   Encoder
   ├─ Extract raw entities & relations (LLM)
   ├─ For each entity:
   │   ├─ Assign hierarchical tags
   │   ├─ Search graph + recent buffer for candidates
   │   └─ LLM decides: create / merge / update
   ├─ Build name_mapping (original → final)
   ├─ Apply name_mapping to all relations
   └─ Write memory_unit to Buffer (SQLite)
        │
        ▼ (session end)
   Session Summary
   ├─ Read encoded units from buffer (not raw conversation)
   ├─ LLM synthesizes structured digest
   └─ Write summary to buffer (type="session_summary")
        │
        ▼ (daily cron)
   Consolidator
   ├─ Read unarchived buffer units
   ├─ Resolve conflicts, merge operations
   ├─ Write to Neo4j graph
   ├─ Spaced repetition scheduling
   ├─ Creative recombination
   └─ Graph hygiene (merge duplicates, suppress noise)
```

## Comparison with Other Systems

| Feature | Brain-Mem | mem0 | Letta (MemGPT) |
|---|:---:|:---:|:---:|
| Cognitive science architecture | ✅ Full pipeline | ❌ | ❌ |
| Knowledge graph storage | ✅ Neo4j | ❌ Key-value | ❌ |
| Layered storage (graph + files) | ✅ | ❌ | ❌ |
| Hierarchical tag taxonomy | ✅ 2-level tree | ❌ | ❌ |
| Entity name resolution & mapping | ✅ LLM-driven | ❌ | ❌ |
| Multi-path retrieval (5 strategies) | ✅ | ❌ Similarity only | ❌ Similarity only |
| Vector semantic search | ✅ Native Neo4j | ✅ | ✅ |
| Sleep consolidation | ✅ Daily cron | ❌ | ❌ |
| Spaced repetition | ✅ Anki-style | ❌ | ❌ |
| Creative recombination | ✅ LLM-driven | ❌ | ❌ |
| Emotional resonance | ✅ Dynamic weights | ❌ | ❌ |
| Prospective memory | ✅ Time + event triggers | ❌ | ❌ |
| Natural forgetting / decay | ✅ | ❌ | ❌ |
| Session summaries (cross-session) | ✅ Buffer-based | ❌ | ✅ |
| Entity lifecycle management | ✅ LLM-driven | ❌ | ❌ |
| Graph hygiene (auto-cleanup) | ✅ LLM-driven | ❌ | ❌ |
| Working memory (per-session) | ✅ | ❌ | ✅ |
| User profile (LLM-enriched) | ✅ | ❌ | ❌ |
| Multi-tenant support | ✅ | ✅ | ❌ |

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check and version info |
| `/logs` | GET | View recent activity logs (`?n=50`) |
| `/hooks/session-start` | POST | Initialize session, load working memory |
| `/hooks/before-query` | POST | Retrieve relevant memories for a query |
| `/hooks/after-response` | POST | Process and encode new memories from conversation |
| `/hooks/session-end` | POST | Generate session summary, destroy working memory |
| `/hooks/consolidate` | POST | Trigger memory consolidation (daily cron) |
| `/hooks/backfill-embeddings` | POST | One-time backfill for nodes without embeddings |

### Example: Full Session Lifecycle

```bash
# 1. Start a session — loads working memory
curl -X POST http://localhost:8100/hooks/session-start \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "default", "user_id": "alice", "session_id": "sess-001"}'

# 2. Query with memory context
curl -X POST http://localhost:8100/hooks/before-query \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "query": "What was my diet plan?"
  }'

# 3. Encode a memory after AI response
curl -X POST http://localhost:8100/hooks/after-response \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "user_message": "I decided to switch jobs next month",
    "assistant_response": "Got it, I will help you prepare."
  }'

# 4. End session — generates summary from encoded buffer data
curl -X POST http://localhost:8100/hooks/session-end \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "default", "user_id": "alice", "session_id": "sess-001"}'
```

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
git clone https://github.com/iCanDoAllThingszz/brain-mem.git
cd brain-mem
cp config.yaml.example config.yaml
# Edit config.yaml with your LLM API credentials and Neo4j password
docker compose up -d
# Service available at http://localhost:8100
```

### Option 2: Manual Setup

```bash
git clone https://github.com/iCanDoAllThingszz/brain-mem.git
cd brain-mem
cp config.yaml.example config.yaml
# Edit config.yaml

pip install -r requirements.txt

# Start Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:5

# Start Brain-Mem
python -m uvicorn server.app:app --host 0.0.0.0 --port 8100
```

### Setup Consolidation Cron

```bash
# Run consolidation daily at 1:30 AM
echo '30 1 * * * curl -s -X POST http://localhost:8100/hooks/consolidate \
  -H "Content-Type: application/json" \
  -d '"'"'{"tenant_id":"default","user_id":"your_user_id"}'"'"' \
  >> /path/to/consolidation.log 2>&1' | crontab -
```

## Project Structure

```
brain-mem/
├── server/
│   ├── app.py                    # FastAPI application, all API endpoints
│   ├── activity_log.py           # Activity logging utility
│   ├── engine/
│   │   ├── perceiver.py          # 👁️ Sensory cortex — filter & classify
│   │   ├── evaluator.py          # 🧪 Prefrontal cortex — evaluate worthiness
│   │   ├── encoder.py            # 🏗️ Hippocampus — entity lifecycle + session summary
│   │   ├── retriever.py          # 🔍 Multi-path memory retrieval
│   │   ├── consolidator.py       # 💤 Sleep consolidation & graph hygiene
│   │   ├── working_memory.py     # 🎯 Per-session context cache (optimized single-scan)
│   │   ├── prospective_checker.py# ⏰ Future memory triggers
│   │   ├── profile_updater.py    # 👤 LLM-driven user profile enrichment
│   │   ├── log_writer.py         # 📝 Categorized file logging
│   │   ├── embedding_client.py   # 🔢 Async embedding with LRU cache
│   │   └── llm_client.py         # 🤖 Shared LLM client
│   ├── storage/
│   │   ├── graph.py              # Neo4j graph operations + vector index + hierarchy expansion
│   │   ├── buffer.py             # SQLite buffer (type-filtered reads)
│   │   ├── tag_dict.py           # Hierarchical tag dictionary
│   │   └── user_profile.py       # Persistent user profile store
│   └── models/
│       ├── node.py               # MemoryNode data model
│       └── relation.py           # Relation data model
├── openclaw-plugin/
│   └── index.ts                  # OpenClaw integration plugin (sequential hook execution)
├── benchmark/
│   └── run_benchmark.py          # Automated test suite (6 dimensions)
├── config.yaml.example           # Configuration template
├── docker-compose.yml            # One-command deployment
├── Dockerfile                    # Container build
├── demo.py                       # Full pipeline demo script
├── requirements.txt              # Python dependencies
└── README.md                     # You are here
```

## Configuration

Copy `config.yaml.example` to `config.yaml` and fill in your credentials:

```yaml
neo4j:
  uri: "bolt://localhost:7687"
  user: "neo4j"
  password: "your_password"

llm:
  base_url: "https://api.openai.com/v1"  # Any OpenAI-compatible API
  api_key: "your_api_key"
  model: "gpt-4o"

embedding:
  base_url: "https://api.openai.com/v1"
  api_key: "your_api_key"
  model: "text-embedding-3-small"
```

> ⚠️ `config.yaml` is gitignored. Never commit credentials.

## Tech Stack

- **Runtime**: Python 3.11+ / FastAPI / Uvicorn
- **Graph Database**: Neo4j 5.x (knowledge graph + native vector index)
- **Buffer**: SQLite (lightweight, zero-config, type-filtered reads)
- **LLM**: Any OpenAI-compatible API
- **Embeddings**: Any embedding API (default dimension: 1536)
- **Plugin**: TypeScript (OpenClaw integration)

## Roadmap

- [ ] Web UI for graph visualization and management
- [ ] Multi-user collaboration memory
- [ ] Plugin marketplace for custom perceiver/evaluator rules
- [ ] Streaming retrieval for real-time applications
- [ ] Memory import/export (JSON, Markdown)
- [ ] Prometheus metrics and Grafana dashboard

## License

[MIT](LICENSE)

---

<p align="center">
  <em>"The brain is not a vessel to be filled, but a fire to be kindled." — Plutarch</em>
</p>
