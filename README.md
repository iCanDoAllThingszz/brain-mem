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

## Overview

Brain-Mem is a production-grade memory system that faithfully models how the **human brain** processes, stores, consolidates, and retrieves memories. Unlike simple vector databases or key-value stores, Brain-Mem implements cognitive science mechanisms including selective encoding, sleep consolidation, spaced repetition, emotional resonance, prospective memory, and natural forgetting.

**Key Differentiators:**
- 🧠 **Cognitive Architecture** — Maps brain regions (hippocampus, prefrontal cortex, amygdala) to system components
- 🏗️ **Layered Storage** — Knowledge graph for cognition, file system for detailed logs
- 🔄 **Sleep Consolidation** — Batch processing that strengthens important memories and prunes noise
- 🎯 **Multi-Path Retrieval** — 5 retrieval strategies with emotional resonance and failure compensation
- ⏰ **Prospective Memory** — Time-based and event-based future reminders
- 📊 **Spaced Repetition** — Automatic review scheduling to prevent forgetting
- 🔗 **Entity Resolution** — LLM-driven name mapping and relation alignment

## Why Brain-Mem?

Most AI memory systems treat memory as a flat database: store everything, retrieve by similarity. The human brain works fundamentally differently:

| Human Brain | Brain-Mem Implementation |
|---|---|
| **Selective encoding** — Not everything gets stored | Perceiver filters noise, Evaluator gates by importance |
| **Sleep consolidation** — Memories strengthen during rest | Consolidator batch-processes buffer → graph with conflict resolution |
| **Multi-path retrieval** — Recall by name, emotion, context | 5 retrieval strategies + emotional resonance weighting |
| **Natural forgetting** — Prevents information overload | Decay mechanism with importance-weighted half-lives |
| **Prospective memory** — "Remind me when X happens" | Time and event-based triggers stored in graph |
| **Cross-session continuity** — Never starts from scratch | Session summaries bridge conversations |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenAI-compatible LLM API (OpenAI, Azure, local models via vLLM/Ollama)
- 2GB RAM minimum, 4GB recommended

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/brain-mem.git
cd brain-mem

# Copy and configure
cp config.yaml.example config.yaml
# Edit config.yaml with your LLM API credentials

# Start services
docker compose up -d

# Verify health
curl http://localhost:8100/health
```

**Services:**
- Brain-Mem API: `http://localhost:8100`
- Neo4j Browser: `http://localhost:7474` (user: `neo4j`, password: from `NEO4J_PASSWORD` env var)

### Configuration

Edit `config.yaml`:

```yaml
neo4j:
  uri: "bolt://neo4j:7687"  # Use "bolt://localhost:7687" for local setup
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

### Setup Consolidation Cron

Memory consolidation should run daily (mimics sleep):

```bash
# Add to crontab (runs at 1:30 AM daily)
30 1 * * * curl -X POST http://localhost:8100/hooks/consolidate \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"default","user_id":"your_user"}' \
  >> /var/log/brain-mem-consolidation.log 2>&1
```

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Incoming Message                         │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────▼────────────────┐
         │  👁️ Perceiver                  │  Filters noise, classifies
         │  (Sensory Cortex + Thalamus)  │  Routes: cognition vs logs
         └───────────────┬────────────────┘
                         │
         ┌───────────────▼────────────────┐
         │  🧪 Evaluator                  │  Scores importance, novelty
         │  (Prefrontal + Amygdala)      │  Gates long-term storage
         └───────────────┬────────────────┘
                         │
         ┌───────────────▼────────────────┐
         │  🏗️ Encoder                    │  Entity resolution
         │  (Hippocampus)                │  Name mapping, relations
         └─────┬──────────────────┬───────┘
               │                  │
    ┌──────────▼─────┐   ┌───────▼────────┐
    │ 📦 Buffer       │   │ 📝 File Logs   │
    │ (SQLite)        │   │ (Markdown)     │
    └──────────┬──────┘   └────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │  💤 Consolidator                    │  Sleep consolidation
    │  (Buffer → Graph)                   │  Spaced repetition
    └──────────┬──────────────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │  📊 Knowledge Graph (Neo4j)         │  Long-term memory
    │  + Vector Index                     │  Entities + Relations
    └─────────────────────────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │  🔍 Retriever                       │  Multi-path recall
    │  (5 strategies + emotional)         │  Context synthesis
    └─────────────────────────────────────┘
```

### Component Mapping

| Brain Region | Component | Function |
|---|---|---|
| **Sensory Cortex + Thalamus** | Perceiver | Filters noise, classifies information type |
| **Prefrontal Cortex + Amygdala** | Evaluator | Scores importance, novelty, emotional significance |
| **Hippocampus** | Encoder | Entity lifecycle, name resolution, relation mapping |
| **Sleep Consolidation** | Consolidator | Buffer→Graph transfer, conflict resolution, spaced repetition |
| **Long-term Memory** | Neo4j Graph | Persistent knowledge storage with vector search |
| **Working Memory** | Working Memory | Per-session context cache |
| **Prospective Memory** | Prospective Checker | Future-oriented reminders |

## Core Features

### 1. Layered Storage Architecture

The brain doesn't store a grocery list the same way it stores a life decision. Brain-Mem uses a three-tier storage model:

**Knowledge Graph (Neo4j)** — High-level cognition
- Goals, decisions, relationships, milestones, insights
- Entities with importance ≥ 5.0
- Vector embeddings for semantic search

**File System (Markdown)** — Detailed logs
- Diet records, exercise logs, interview notes
- Trading records, learning journals
- Organized by category and date

**Buffer (SQLite)** — Short-term staging
- Encoded memory units awaiting consolidation
- Session summaries for cross-session continuity
- Type-filtered reads (memory vs summary)

**Example:**
```
User: "I had an apple for breakfast"

❌ Without layered storage:
   → Creates entities: Apple, User, BreakfastFruitHabit
   → Graph polluted with trivial food items

✅ With layered storage:
   → Appends to memory/logs/diet/2026-03-22.md
   → Updates graph: DietPlan.last_diet_log = "2026-03-22"
   → Graph stays clean, detail preserved
```

### 2. Entity Resolution & Name Mapping

The encoder doesn't blindly create nodes. It follows a rigorous lifecycle:

1. **Hierarchical tag assignment** — Classify entity using two-level tag tree
2. **Same-type retrieval** — Search existing nodes with matching tags
3. **LLM resolution** — Decide: `create`, `merge`, or `update`
4. **Name mapping** — Build `original_name → final_name` mapping
5. **Relation alignment** — Apply mapping to all relations
6. **Embedding generation** — Auto-generate vector embeddings

**Example:**
```
User: "凡哥是我同事"
→ "凡哥" resolves to existing node "刘凡"
→ Relation corrected: from_name="刘凡" (not "凡哥")
→ No orphaned references
```

### 3. Multi-Path Retrieval

Human memory retrieval isn't a single mechanism. Brain-Mem implements 5 strategies:

| Path | Strategy | Use Case |
|---|---|---|
| **A** | Exact name match | Direct entity lookup |
| **B** | Alias match | "that AI project" → matches project alias |
| **C** | Fuzzy keyword | Partial matches, related terms |
| **D** | Dormant reactivation | Resurface old memories |
| **E** | Vector semantic | Meaning-based via embeddings |

**Additional mechanisms:**
- **Emotional resonance** — Emotions shift scoring weights dynamically
- **Failure compensation** — Auto-expands to 3-hop graph traversal if results insufficient

### 4. Sleep Consolidation

Mimics the brain's sleep-phase memory consolidation with 12 steps:

1. **Buffer read** — Fetch unarchived memory units
2. **Entity upsert** — Create/merge/update nodes in graph
3. **Relation creation** — Build knowledge graph connections
4. **Embedding generation** — Auto-generate vectors for new nodes
5. **Pattern discovery** — LLM finds cross-event patterns
6. **Conflict resolution** — Resolve contradictory memories
7. **Orphan repair** — Connect isolated nodes
8. **Creative recombination** — Discover non-obvious insights
9. **Graph hygiene** — Merge duplicates, suppress noise
10. **Implicit relations** — Infer missing connections
11. **Memory decay** — Apply forgetting curve
12. **Spaced repetition** — Schedule reviews for important memories

**Trigger:** Daily cron job (recommended: 1:30 AM)


### 5. Spaced Repetition

Prevents important memories from fading using Ebbinghaus forgetting curve:

- **Review intervals:** 1 → 3 → 7 → 21 days, then doubling
- **Auto-strengthening:** Consolidator directly boosts `retrieval_strength`
- **Decay resistance:** Important nodes (importance ≥ 6.0) get periodic reviews
- **No user action needed:** System automatically maintains memory strength

### 6. Prospective Memory

Future-oriented reminders with two trigger types:

**Time-based:**
```
"Remind me at 3pm tomorrow to call the client"
→ Stored with trigger_time, fires at specified time
```

**Event-based:**
```
"When I mention the project, remind me to update the timeline"
→ Fires when query matches trigger keywords
→ Supports repeat counts (1=one-time, 0=infinite, N=limited)
```

## API Reference

### Core Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check and version |
| `/logs?n=50` | GET | Recent activity logs |
| `/hooks/session-start` | POST | Initialize session, load working memory |
| `/hooks/before-query` | POST | Retrieve memories for query |
| `/hooks/after-response` | POST | Encode new memories |
| `/hooks/session-end` | POST | Generate session summary |
| `/hooks/consolidate` | POST | Trigger consolidation (cron) |
| `/hooks/check-prospective` | POST | Check time-based reminders |
| `/hooks/backfill-embeddings` | POST | Generate missing embeddings |

### Status Check Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/hooks/status/session-start` | GET | Check session-start hook logs |
| `/hooks/status/before-query` | GET | Check before-query hook logs |
| `/hooks/status/after-response` | GET | Check after-response hook logs |
| `/hooks/status/session-end` | GET | Check session-end hook logs |

### Example: Full Session Lifecycle

```bash
# 1. Start session
curl -X POST http://localhost:8100/hooks/session-start \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "user_profile": {"name": "Alice", "role": "engineer"}
  }'

# 2. Query with memory context
curl -X POST http://localhost:8100/hooks/before-query \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "query": "What was my career goal?"
  }'

# 3. Encode memory after conversation
curl -X POST http://localhost:8100/hooks/after-response \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001",
    "user_message": "I decided to switch to AI research",
    "assistant_response": "Great choice! I will help you prepare."
  }'

# 4. End session
curl -X POST http://localhost:8100/hooks/session-end \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice",
    "session_id": "sess-001"
  }'

# 5. Trigger consolidation (daily cron)
curl -X POST http://localhost:8100/hooks/consolidate \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "default",
    "user_id": "alice"
  }'
```


## Project Structure

```
brain-mem/
├── server/
│   ├── app.py                      # FastAPI application & endpoints
│   ├── activity_log.py             # Activity logging
│   ├── engine/
│   │   ├── perceiver.py            # 👁️ Filter & classify
│   │   ├── evaluator.py            # 🧪 Evaluate importance
│   │   ├── encoder.py              # 🏗️ Entity lifecycle
│   │   ├── retriever.py            # 🔍 Multi-path retrieval
│   │   ├── consolidator.py         # 💤 Sleep consolidation
│   │   ├── working_memory.py       # 🎯 Session context
│   │   ├── prospective_checker.py  # ⏰ Future reminders
│   │   ├── profile_updater.py      # 👤 User profile
│   │   ├── log_writer.py           # 📝 File logging
│   │   ├── embedding_client.py     # 🔢 Embeddings
│   │   └── llm_client.py           # 🤖 LLM client
│   ├── storage/
│   │   ├── graph.py                # Neo4j operations
│   │   ├── buffer.py               # SQLite buffer
│   │   ├── tag_dict.py             # Tag hierarchy
│   │   └── user_profile.py         # Profile store
│   └── models/
│       ├── node.py                 # Node model
│       └── relation.py             # Relation model
├── openclaw-plugin/
│   └── index.ts                    # OpenClaw integration
├── config.yaml.example             # Config template
├── docker-compose.yml              # Docker deployment
├── Dockerfile                      # Container build
├── requirements.txt                # Dependencies
└── README.md                       # Documentation
```

## Tech Stack

- **Runtime:** Python 3.11+ / FastAPI / Uvicorn
- **Graph Database:** Neo4j 5.x (native vector index)
- **Buffer:** SQLite (zero-config, type-filtered)
- **LLM:** OpenAI-compatible API
- **Embeddings:** text-embedding-3-small (1536-dim)
- **Plugin:** TypeScript (OpenClaw)

## Comparison

| Feature | Brain-Mem | mem0 | Letta |
|---|:---:|:---:|:---:|
| Cognitive architecture | ✅ | ❌ | ❌ |
| Knowledge graph | ✅ Neo4j | ❌ | ❌ |
| Layered storage | ✅ | ❌ | ❌ |
| Entity resolution | ✅ LLM | ❌ | ❌ |
| Multi-path retrieval | ✅ 5 paths | ❌ | ❌ |
| Sleep consolidation | ✅ | ❌ | ❌ |
| Spaced repetition | ✅ | ❌ | ❌ |
| Emotional resonance | ✅ | ❌ | ❌ |
| Prospective memory | ✅ | ❌ | ❌ |
| Natural forgetting | ✅ | ❌ | ❌ |
| Session summaries | ✅ | ❌ | ✅ |
| Multi-tenant | ✅ | ✅ | ❌ |


## Development

### Local Setup

```bash
# Clone repository
git clone https://github.com/yourusername/brain-mem.git
cd brain-mem

# Install dependencies
pip install -r requirements.txt

# Start Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your_password \
  neo4j:5

# Configure
cp config.yaml.example config.yaml
# Edit config.yaml

# Run server
python -m uvicorn server.app:app --reload --port 8100
```

### Environment Variables

```bash
# Override config.yaml with environment variables
export NEO4J_URI="bolt://localhost:7687"
export NEO4J_PASSWORD="your_password"
export LLM_API_KEY="sk-..."
```

## OpenClaw Integration

Brain-Mem includes an OpenClaw plugin for seamless integration:

```typescript
// openclaw-plugin/index.ts
// Hooks: session-start, before-query, after-response, session-end
```

Install in OpenClaw:
```bash
cd openclaw-plugin
npm install
# Configure in OpenClaw settings
```

## Troubleshooting

**Neo4j connection failed:**
```bash
# Check Neo4j is running
docker ps | grep neo4j
# Verify credentials in config.yaml
```

**Embeddings generation slow:**
```bash
# Check embedding API endpoint
curl -X POST https://api.openai.com/v1/embeddings \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"input":"test","model":"text-embedding-3-small"}'
```

**Memory not consolidating:**
```bash
# Check consolidation logs
curl http://localhost:8100/logs?n=100 | grep consolidation
# Manually trigger
curl -X POST http://localhost:8100/hooks/consolidate \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"default","user_id":"your_user"}'
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Citation

If you use Brain-Mem in your research, please cite:

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
  <em>"The brain is not a vessel to be filled, but a fire to be kindled." — Plutarch</em>
</p>
