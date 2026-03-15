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
                    │  Pronoun resolution, deduplication           │
                    └──────┬───────────────────────┬──────────────┘
                           │                       │
              ┌────────────▼─────────┐  ┌─────────▼──────────────┐
              │  📊 Knowledge Graph  │  │  📝 File Logs          │
              │  (Neo4j + Vector)    │  │  diet/exercise/trading  │
              │  Goals, decisions,   │  │  interview/learning     │
              │  relationships       │  │  Detailed daily records │
              └────────────┬─────────┘  └─────────┬──────────────┘
                           │                       │
              ┌────────────▼───────────────────────▼──────────────┐
              │  💤 Consolidator (Sleep Consolidation)            │
              │  Spaced repetition, creative recombination        │
              │  Graph hygiene, interference forgetting           │
              │  Runs daily via cron                              │
              └───────────────────────────────────────────────────┘

              ┌───────────────────────────────────────────────────┐
              │  🔍 Retriever (Multi-Path Recall)                 │
              │  5 strategies: exact → alias → fuzzy → dormant    │
              │  → vector semantic | Emotional resonance          │
              └───────────────────────────────────────────────────┘

              ┌───────────────────────────────────────────────────┐
              │  🎯 Working Memory (Session Context)              │
              │  Active goals, reminders, emotional baseline      │
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
| Hippocampus | **Encoder** | `encoder.py` | LLM-driven entity lifecycle management. Resolves pronouns to real names, deduplicates via tag-based grouping, makes create/merge/update decisions in one LLM call |
| Short-term Buffer | **Buffer** | `buffer.py` | SQLite-based temporary storage with embedding support. Holds recent memories before consolidation |
| Sleep Consolidation | **Consolidator** | `consolidator.py` | Daily batch process: spaced repetition scheduling (1→3→7→21 days), creative recombination, LLM-driven graph hygiene (merge duplicates, suppress noise) |
| Memory Retrieval | **Retriever** | `retriever.py` | 5-path retrieval with emotional resonance weighting and failure compensation. Synthesizes retrieved fragments into factual context |
| Working Memory | **Working Memory** | `working_memory.py` | Per-session context cache: active goals, pending reminders, emotional baseline. Loaded on session start |
| Prospective Memory | **Prospective Checker** | `prospective_checker.py` | Future-oriented memory: time-based triggers ("remind at 3pm") and event-based triggers ("remind when X happens") |
| Embedding System | **Embedding Client** | `embedding_client.py` | Async embedding generation with LRU cache (1000 entries). Powers vector semantic search |
| Log System | **Log Writer** | `log_writer.py` | Writes detailed logs to categorized files (diet, exercise, interview, trading, learning) while maintaining graph index pointers |

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

### 2. Intelligent Encoding (Entity Lifecycle Management)

The encoder doesn't blindly create new nodes. It follows a rigorous lifecycle:

1. **Tag-based grouping** — Classify the entity by semantic tags
2. **Same-type retrieval** — Search existing nodes with matching tags
3. **LLM resolution** — One LLM call decides: `create` (new entity), `merge` (combine with existing), or `update` (modify existing)
4. **Pronoun resolution** — "我" / "I" → actual user name (hardcoded fallback + LLM-driven)
5. **Embedding generation** — Auto-generates vector embedding on encode

Budget: **1 LLM call per encode operation** — efficient by design.

### 3. Multi-Path Retrieval (5 Strategies)

Human memory retrieval isn't a single mechanism. You might recall something by name, by association, or by a vague feeling. Brain-Mem implements 5 retrieval paths:

| Path | Strategy | When It Helps |
|---|---|---|
| A | **Exact name match** | Direct entity lookup |
| B | **Alias match** | "that AI project" → matches alias of a named project |
| C | **Fuzzy keyword search** | Partial matches, related terms |
| D | **Dormant reactivation** | Resurfaces nodes not accessed recently |
| E | **Vector semantic search** | Meaning-based retrieval via embeddings |

Additional mechanisms:
- **Emotional resonance** — Non-neutral emotions dynamically shift scoring weights (relevance × 0.4 + emotional × 0.2 instead of default × 0.5 / × 0.1)
- **Retrieval failure compensation** — If initial search returns too few results, auto-expands to 3-hop graph traversal
- **Multi-hop traversal** — Default 1-2 hops, expands on compensation


### 4. Cognitive Science Features

These aren't buzzwords — each maps to a real cognitive mechanism with a concrete implementation:

| Mechanism | Brain Basis | Implementation |
|---|---|---|
| **Spaced Repetition** | Ebbinghaus forgetting curve | Review intervals: 1→3→7→21 days, then doubling. Consolidator schedules next review based on access patterns |
| **Creative Recombination** | Sleep-phase insight generation | During consolidation, LLM discovers non-obvious connections between memories (max 2 attempts, temperature=0.7, confidence≥0.5) |
| **Memory Reconsolidation** | Memory updating on recall | User corrections auto-update existing memories without evaluation gate. If target entity doesn't exist, auto-creates it |
| **Interference Forgetting** | Competing memory traces | Similar memories naturally compete; weaker traces decay faster when stronger alternatives exist |
| **Natural Decay** | Time-based forgetting | Unused memories gradually lose retrieval strength via `decay_factor`. Keeps memory fresh and relevant |
| **Emotional Resonance** | Amygdala modulation | Emotionally tagged memories get retrieval priority. Non-neutral emotions shift scoring weights dynamically |
| **Prospective Memory** | Future intention encoding | Time-based ("remind at 3pm") and event-based ("remind when X happens") triggers, written directly to graph |
| **Motivated Forgetting** | Suppression mechanism | Nodes can be suppressed (hidden, never deleted) — recoverable but out of active retrieval |

### 5. LLM-Driven Graph Hygiene

Keeping a knowledge graph clean is hard. Brain-Mem uses LLM intelligence instead of brittle rules:

- **Consolidator reviews** graph nodes in batches (max 30 nodes per batch, max 3 LLM calls per consolidation run)
- **Decisions**: merge duplicates, suppress noise, keep uncertain
- **Anti-misfire priority**: When the LLM returns "unsure" → **always keep the node**. False deletion is worse than clutter.
- **Only one hardcoded rule**: pronoun → username mapping. Everything else is LLM-decided.

### 6. Working Memory

Each conversation session gets its own working memory context:

- **Active goals** — What the user is currently working toward
- **Pending reminders** — Prospective memory triggers waiting to fire
- **Emotional baseline** — Current emotional state for resonance scoring
- Loaded on `session-start`, provides context for perceiver, evaluator, and retriever

### 7. Vector Search

Built on Neo4j 5.x native vector index — no separate vector database needed:

- **Graph nodes**: Cosine similarity search on 1536-dimensional embeddings
- **Buffer records**: Numpy brute-force cosine (optimal for <1000 items, no ANN overhead)
- **Vector field composition**: Graph uses `"name: summary"` concatenation; buffer uses perceiver rewrite text
- **Auto-generation**: Embeddings created on encode; backfill endpoint for existing nodes

## Storage Architecture

```
Neo4j (Knowledge Graph)           SQLite (Buffer)               File System (Logs)
┌──────────────────────┐    ┌───────────────────────┐    ┌──────────────────────────┐
│ MemoryNode            │    │ memory_buffer          │    │ memory/logs/             │
│ ├─ id, name, summary │    │ ├─ id, data, embedding │    │ ├── diet/YYYY-MM-DD.md   │
│ ├─ zone, importance  │    │ ├─ importance, archived│    │ ├── exercise/...          │
│ ├─ tags[], aliases[] │    │ ├─ timestamp, date     │    │ ├── interview/...         │
│ ├─ embedding[1536]   │    │ └─ tenant_id, user_id  │    │ ├── trading/...           │
│ ├─ emotional_tag     │    └───────────────────────┘    │ ├── learning/...          │
│ ├─ decay_factor      │                                  │ └── general/...           │
│ ├─ retrieval_strength│                                  └──────────────────────────┘
│ ├─ confidence        │
│ ├─ access_count      │
│ └─ status            │
└──────────────────────┘
```

**Memory Zones:**
- `episodic` — Personal events and experiences
- `semantic` — Facts, concepts, knowledge
- `procedural` — Skills, habits, how-to knowledge

## Comparison with Other Systems

| Feature | Brain-Mem | mem0 | Letta (MemGPT) |
|---|:---:|:---:|:---:|
| Cognitive science architecture | ✅ Full pipeline | ❌ | ❌ |
| Knowledge graph storage | ✅ Neo4j | ❌ Key-value | ❌ |
| Layered storage (graph + files) | ✅ | ❌ | ❌ |
| Multi-path retrieval (5 strategies) | ✅ | ❌ Similarity only | ❌ Similarity only |
| Vector semantic search | ✅ Native Neo4j | ✅ | ✅ |
| Sleep consolidation | ✅ Daily cron | ❌ | ❌ |
| Spaced repetition | ✅ Anki-style | ❌ | ❌ |
| Creative recombination | ✅ LLM-driven | ❌ | ❌ |
| Emotional resonance | ✅ Dynamic weights | ❌ | ❌ |
| Prospective memory | ✅ Time + event triggers | ❌ | ❌ |
| Natural forgetting / decay | ✅ | ❌ | ❌ |
| Memory reconsolidation | ✅ | ❌ | ❌ |
| Entity lifecycle management | ✅ LLM-driven | ❌ | ❌ |
| Graph hygiene (auto-cleanup) | ✅ LLM-driven | ❌ | ❌ |
| Working memory (per-session) | ✅ | ❌ | ✅ |
| Multi-tenant support | ✅ | ✅ | ❌ |


## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check and version info |
| `/logs` | GET | View recent activity logs (`?n=50`) |
| `/hooks/session-start` | POST | Initialize session, load working memory |
| `/hooks/before-query` | POST | Retrieve relevant memories for a query |
| `/hooks/after-response` | POST | Process and encode new memories from conversation |
| `/hooks/consolidate` | POST | Trigger memory consolidation (daily cron) |
| `/hooks/backfill-embeddings` | POST | One-time backfill for nodes without embeddings |

### Example: Retrieve Memories

```bash
# Start a session
curl -X POST http://localhost:8100/hooks/session-start \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "default", "user_id": "alice", "session_id": "sess-001"}'

# Query with memory context
curl -X POST http://localhost:8100/hooks/before-query \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "query": "What was my diet plan?"
  }'
# Returns: {"code": 0, "data": {"context": "Alice's diet plan targets 1600 calories daily..."}}
```

### Example: Encode a Memory

```bash
curl -X POST http://localhost:8100/hooks/after-response \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "user_message": "I decided to switch jobs next month",
    "assistant_message": "Got it, I will help you prepare."
  }'
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
# Run consolidation daily at 1:30 AM (adjust timezone as needed)
echo '30 17 * * * curl -s -X POST http://localhost:8100/hooks/consolidate \
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
│   │   ├── encoder.py            # 🏗️ Hippocampus — entity lifecycle management
│   │   ├── retriever.py          # 🔍 Multi-path memory retrieval
│   │   ├── consolidator.py       # 💤 Sleep consolidation & graph hygiene
│   │   ├── working_memory.py     # 🎯 Per-session context cache
│   │   ├── prospective_checker.py# ⏰ Future memory triggers
│   │   ├── log_writer.py         # 📝 Categorized file logging
│   │   ├── embedding_client.py   # 🔢 Async embedding with LRU cache
│   │   └── llm_client.py         # 🤖 Shared LLM client
│   ├── storage/
│   │   ├── graph.py              # Neo4j graph operations + vector index
│   │   ├── buffer.py             # SQLite buffer storage
│   │   └── tag_dict.py           # Tag dictionary for entity grouping
│   └── models/
│       ├── node.py               # MemoryNode data model
│       └── relation.py           # Relation data model
├── openclaw-plugin/
│   └── index.ts                  # OpenClaw integration plugin
├── benchmark/
│   └── run_benchmark.py          # Automated test suite (6 dimensions)
├── docs/
│   └── V3-DESIGN.md             # v3 layered storage design document
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
- **Buffer**: SQLite (lightweight, zero-config)
- **LLM**: Any OpenAI-compatible API
- **Embeddings**: Any embedding API (default dimension: 1536)

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
