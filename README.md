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

## 🎯 Overview

Brain-Mem is a production-grade memory system that faithfully models how the **human brain** processes, stores, consolidates, and retrieves memories. Unlike simple vector databases or key-value stores, Brain-Mem implements cognitive science mechanisms including selective encoding, sleep consolidation, spaced repetition, emotional resonance, prospective memory, and natural forgetting.

Built as an **OpenClaw plugin**, Brain-Mem seamlessly integrates with AI agents through event-driven hooks, providing context-aware memory without requiring code changes to your agent.

### Key Differentiators

- 🧠 **Cognitive Architecture** — Maps brain regions (hippocampus, prefrontal cortex, amygdala) to system components
- 🏗️ **Layered Storage** — Knowledge graph for cognition, file system for detailed logs, buffer for staging
- 🔄 **Sleep Consolidation** — Batch processing that strengthens important memories and prunes noise
- 🎯 **Multi-Path Retrieval** — 5 retrieval strategies with emotional resonance and failure compensation
- ⏰ **Prospective Memory** — Time-based and event-based future reminders
- 📊 **Spaced Repetition** — Automatic review scheduling based on Ebbinghaus forgetting curve
- 🔗 **Entity Resolution** — LLM-driven name mapping and deduplication
- 🔌 **OpenClaw Plugin** — Zero-code integration via hooks

---

## 🤔 Why Brain-Mem?

Most AI memory systems treat memory as a flat database: store everything, retrieve by similarity. The human brain works fundamentally differently:

| Human Brain | Brain-Mem Implementation |
|-------------|--------------------------|
| **Selective encoding** — Not everything gets stored | Perceiver filters noise, Evaluator gates by importance |
| **Sleep consolidation** — Memories strengthen during rest | Consolidator batch-processes buffer → graph with 12-step pipeline |
| **Multi-path retrieval** — Recall by name, emotion, context | 5 retrieval strategies + emotional resonance weighting |
| **Natural forgetting** — Prevents information overload | Decay mechanism with importance-weighted half-lives |
| **Prospective memory** — "Remind me when X happens" | Time and event-based triggers stored in graph |
| **Entity resolution** — "John" = "John Smith" = "my colleague" | LLM-driven name mapping with hierarchical tag search |
| **Cross-session continuity** — Never starts from scratch | Session summaries bridge conversations |

### Comparison with Other Systems

| Feature | Brain-Mem | mem0 | Letta | Vector DBs |
|---------|:---------:|:----:|:-----:|:----------:|
| Cognitive architecture | ✅ | ❌ | ❌ | ❌ |
| Knowledge graph | ✅ Neo4j | ❌ | ❌ | ❌ |
| Layered storage | ✅ 3-tier | ❌ | ❌ | ❌ |
| Entity resolution | ✅ LLM | ❌ | ❌ | ❌ |
| Multi-path retrieval | ✅ 5 paths | ❌ Vector only | ❌ | ❌ Vector only |
| Sleep consolidation | ✅ 12 steps | ❌ | ❌ | ❌ |
| Spaced repetition | ✅ | ❌ | ❌ | ❌ |
| Emotional resonance | ✅ | ❌ | ❌ | ❌ |
| Prospective memory | ✅ | ❌ | ❌ | ❌ |
| Natural forgetting | ✅ Decay | ❌ | ❌ | ❌ |
| Session summaries | ✅ | ❌ | ✅ | ❌ |
| Multi-tenant | ✅ | ✅ | ❌ | Varies |
| OpenClaw plugin | ✅ | ❌ | ❌ | ❌ |

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenAI-compatible LLM API (OpenAI, Azure, MiniMax, or local models via vLLM/Ollama)
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

---

## 🏗️ Architecture

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

### Brain-Inspired Component Mapping

| Brain Region | Component | Function | Implementation |
|--------------|-----------|----------|----------------|
| **Sensory Cortex + Thalamus** | Perceiver | Filters noise, classifies information type | LLM-based classification into `noise`, `command`, `informative` |
| **Prefrontal Cortex + Amygdala** | Evaluator | Scores importance, novelty, emotional significance | Multi-dimensional scoring: task relevance, emotional intensity, novelty |
| **Hippocampus** | Encoder | Entity lifecycle, name resolution, relation mapping | Hierarchical tag search + LLM resolution + name mapping |
| **Sleep Consolidation** | Consolidator | Buffer→Graph transfer, conflict resolution, spaced repetition | 12-step pipeline with pattern discovery and graph hygiene |
| **Long-term Memory** | Neo4j Graph | Persistent knowledge storage with vector search | Graph database + native vector index |
| **Working Memory** | Working Memory | Per-session context cache | In-memory cache with session lifecycle |
| **Prospective Memory** | Prospective Checker | Future-oriented reminders | Time/event-based triggers with repeat counts |

---
## 🎨 Core Features

### 1. Layered Storage Architecture

The brain doesn't store a grocery list the same way it stores a life decision. Brain-Mem uses a three-tier storage model:

**📊 Knowledge Graph (Neo4j)** — High-level cognition
- Goals, decisions, relationships, milestones, insights
- Entities with importance ≥ 5.0
- Vector embeddings for semantic search
- Example: "Career goal: transition to AI research by Q3"

**📝 File System (Markdown)** — Detailed logs
- Diet records, exercise logs, interview notes
- Trading records, learning journals, meeting minutes
- Organized by category and date
- Example: `memory/logs/diet/2026-03-22.md`

**📦 Buffer (SQLite)** — Short-term staging
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
User: "My colleague is working on the AI project"
→ "My colleague" resolves to existing node "John Smith"
→ Relation corrected: from_name="John Smith" (not "My colleague")
→ No orphaned references
```

### 3. Multi-Path Retrieval

Human memory retrieval isn't a single mechanism. Brain-Mem implements 5 strategies:

| Path | Strategy | Use Case | Example |
|------|----------|----------|---------|
| **A** | Exact name match | Direct entity lookup | "John Smith" → finds node |
| **B** | Alias match | Nickname/reference | "that AI project" → matches project alias |
| **C** | Fuzzy keyword | Partial matches | "proj" → finds "AI Project" |
| **D** | Dormant reactivation | Resurface old memories | Retrieves nodes with strength < 2.0 |
| **E** | Vector semantic | Meaning-based | "machine learning work" → finds "AI research" |

**Additional mechanisms:**
- **Emotional resonance** — Current emotion shifts scoring weights dynamically
- **Failure compensation** — Auto-expands to 3-hop graph traversal if results insufficient
- **Composite scoring** — Relevance (40-50%) + Importance (15%) + Recency (15%) + Access Frequency (10%) + Emotional (10-20%)

### 4. Sleep Consolidation

Mimics the brain's sleep-phase memory consolidation with a 12-step pipeline:

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

**Why consolidation matters:**
- **Pattern discovery**: "User mentioned 'deadline stress' 3 times this week → create pattern node"
- **Conflict resolution**: "User said 'I love coffee' yesterday, 'I quit coffee' today → resolve contradiction"
- **Graph hygiene**: "Merge duplicate nodes: 'AI Project' and 'AI project' → single node"

### 5. Spaced Repetition

Prevents important memories from fading using Ebbinghaus forgetting curve:

- **Review intervals:** 1 → 3 → 7 → 21 days, then doubling
- **Auto-strengthening:** Consolidator directly boosts `retrieval_strength`
- **Decay resistance:** Important nodes (importance ≥ 6.0) get periodic reviews
- **No user action needed:** System automatically maintains memory strength

**Mechanism:**
```python
# Decay formula (applied during consolidation)
days_since_access = (now - last_access_time).days
decay_rate = 0.1 if importance >= 6.0 else 0.2
new_strength = old_strength * exp(-decay_rate * days_since_access)

# Spaced repetition scheduling
if importance >= 6.0 and strength < threshold:
    next_review = last_review + interval
    intervals = [1, 3, 7, 21, 42, 84, ...]  # days
```

### 6. Prospective Memory

Future-oriented reminders with two trigger types:

**Time-based:**
```
"Remind me at 3pm tomorrow to call the client"
→ Stored with trigger_time="2026-03-24T15:00:00Z"
→ Fires at specified time (checked at session start)
```

**Event-based:**
```
"When I mention the project, remind me to update the timeline"
→ Fires when query matches trigger keywords
→ Supports repeat counts (1=one-time, 0=infinite, N=limited)
```

**Storage:**
```cypher
CREATE (p:ProspectiveMemory {
  content: "Update project timeline",
  trigger_type: "event",
  trigger_keywords: ["project", "timeline"],
  repeat_count: 1,
  created_at: "2026-03-22T10:00:00Z"
})
```

### 7. Emotional Resonance

Emotions influence memory retrieval:

- **Emotional tagging** — Nodes carry `emotional_tag` (type + intensity)
- **Dynamic weighting** — Current emotion boosts matching memories
- **Encouragement rule** — Negative emotions boost positive memories
- **Intensity scaling** — Higher intensity = stronger influence

**Example:**
```
User emotion: anxious (intensity: 7)
Query: "What should I do?"

Retrieval scoring:
- Node A (calm, importance: 8) → boosted by encouragement rule
- Node B (anxious, importance: 6) → boosted by emotion match
- Node C (neutral, importance: 9) → standard scoring
```


---

## 🔌 OpenClaw Plugin Integration

Brain-Mem integrates seamlessly with OpenClaw through event-driven hooks. No code changes required in your agent.

### Hook Lifecycle

**1. brain-memory-recall** (`message:preprocessed`)
- **Trigger:** Before agent processes user message
- **Actions:** 
  - Calls `/hooks/session-start` (if new session)
  - Calls `/hooks/before-query` (retrieve memories)
- **Injects:** `<working-memory>` and `<retrieved-memories>` XML blocks into prompt
- **Filters:** Skips cron jobs, subagents, heartbeats

**2. brain-memory-capture** (`message:preprocessed`)
- **Trigger:** When user sends message
- **Actions:** Stores message in temporary map for later encoding
- **TTL:** 2 minutes

**3. brain-memory-encode** (`message:sent`)
- **Trigger:** After agent responds successfully
- **Actions:** Calls `/hooks/after-response` with user + assistant messages
- **Pipeline:** Perceiver → Evaluator → Encoder (background processing)

**4. brain-memory-session** (`command:new`)
- **Trigger:** When user starts new conversation
- **Actions:** Calls `/hooks/session-end` to generate summary
- **Cleanup:** Destroys working memory cache

### Installation

```bash
# 1. Install plugin in OpenClaw
cd openclaw-plugin
npm install

# 2. Configure environment variables
export BRAIN_SERVER_URL="http://localhost:8100"
export BRAIN_TENANT_ID="default"
export BRAIN_USER_ID="your_user_id"

# 3. Register plugin in OpenClaw settings
# Add to openclaw.config.json:
{
  "plugins": [
    {
      "name": "brain-memory",
      "path": "./openclaw-plugin"
    }
  ]
}
```

### Hook Configuration

The plugin automatically registers hooks with OpenClaw. Configuration in `openclaw.plugin.json`:

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

### Memory Context Injection

When a user sends a message, the plugin injects memory context:

```xml
<working-memory>
User Profile: Software engineer, interested in AI
Active Goals: Learn reinforcement learning, build chatbot
Recent Context: Discussed transformer architecture yesterday
Emotional Baseline: Motivated, slightly stressed about deadline
</working-memory>

<retrieved-memories>
1. [Goal] Learn reinforcement learning by end of Q2 (importance: 8.5)
2. [Project] Building chatbot with GPT-4 API (importance: 7.0)
3. [Knowledge] Transformer architecture uses self-attention (importance: 6.5)
</retrieved-memories>
```

---

## 📚 API Reference

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
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
|----------|--------|-------------|
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


---

## 📁 Project Structure

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
│   ├── index.ts                    # OpenClaw integration
│   └── openclaw.plugin.json        # Plugin metadata
├── config.yaml.example             # Config template
├── docker-compose.yml              # Docker deployment
├── Dockerfile                      # Container build
├── requirements.txt                # Dependencies
└── README.md                       # Documentation
```

---

## 🛠️ Tech Stack

- **Runtime:** Python 3.11+ / FastAPI / Uvicorn
- **Graph Database:** Neo4j 5.x (native vector index)
- **Buffer:** SQLite (zero-config, type-filtered)
- **LLM:** OpenAI-compatible API (OpenAI, Azure, MiniMax, vLLM, Ollama)
- **Embeddings:** text-embedding-3-small (1536-dim)
- **Plugin:** TypeScript (OpenClaw)

---

## 🚀 Development

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
export EMBEDDING_API_KEY="sk-..."
```

### Docker Deployment

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f brain-mem

# Stop services
docker compose down
```


---

## 🔬 Cognitive Science Background

Brain-Mem is grounded in established cognitive science and neuroscience research:

### Selective Encoding (Craik & Lockhart, 1972)
Not all information receives equal processing depth. Brain-Mem's Perceiver and Evaluator implement levels-of-processing theory, filtering noise and gating storage by importance.

### Sleep Consolidation (Stickgold & Walker, 2005)
Memory consolidation during sleep strengthens important memories and prunes irrelevant ones. Brain-Mem's Consolidator mimics this with batch processing, pattern discovery, and graph hygiene.

### Multi-Store Memory Model (Atkinson & Shiffrin, 1968)
Information flows through sensory → short-term → long-term memory. Brain-Mem implements this with Buffer (short-term) → Graph (long-term) architecture.

### Spreading Activation (Collins & Loftus, 1975)
Memory retrieval activates related concepts. Brain-Mem's multi-path retrieval and 3-hop graph traversal implement spreading activation.

### Forgetting Curve (Ebbinghaus, 1885)
Memory strength decays exponentially over time. Brain-Mem applies decay mechanisms with importance-weighted half-lives.

### Spaced Repetition (Piotr Woźniak, 1985)
Reviewing information at increasing intervals prevents forgetting. Brain-Mem automatically schedules reviews based on importance and access patterns.

### Prospective Memory (Einstein & McDaniel, 1990)
Future-oriented memory for intentions. Brain-Mem implements time-based and event-based triggers.

### Emotional Memory (McGaugh, 2004)
Emotions enhance memory encoding and retrieval. Brain-Mem's emotional resonance mechanism weights retrieval by emotional state.

---

## 🔍 Troubleshooting

**Neo4j connection failed:**
```bash
# Check Neo4j is running
docker ps | grep neo4j

# Verify credentials in config.yaml
# Check Neo4j logs
docker logs neo4j
```

**Embeddings generation slow:**
```bash
# Check embedding API endpoint
curl -X POST https://api.openai.com/v1/embeddings \
  -H "Authorization: Bearer $API_KEY" \
  -d '{"input":"test","model":"text-embedding-3-small"}'

# Consider using local embedding models (e.g., sentence-transformers)
```

**Memory not consolidating:**
```bash
# Check consolidation logs
curl http://localhost:8100/logs?n=100 | grep consolidation

# Manually trigger
curl -X POST http://localhost:8100/hooks/consolidate \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"default","user_id":"your_user"}'

# Check buffer has data
sqlite3 memory/buffer.db "SELECT COUNT(*) FROM memory_units WHERE archived=0"
```

**OpenClaw plugin not working:**
```bash
# Check environment variables
echo $BRAIN_SERVER_URL
echo $BRAIN_TENANT_ID
echo $BRAIN_USER_ID

# Check Brain-Mem server is accessible
curl http://localhost:8100/health

# Check OpenClaw logs for hook execution
```

**High memory usage:**
```bash
# Check Neo4j memory settings in docker-compose.yml
# Adjust NEO4J_server_memory_heap_max__size

# Check buffer size
sqlite3 memory/buffer.db "SELECT COUNT(*) FROM memory_units"

# Run consolidation to move buffer → graph
```


---

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

## 📖 Citation

If you use Brain-Mem in your research, please cite:

```bibtex
@software{brain_mem_2026,
  title = {Brain-Mem: A Cognitive Science-Inspired Memory System for AI Agents},
  year = {2026},
  url = {https://github.com/yourusername/brain-mem}
}
```

---

## 🙏 Acknowledgments

Brain-Mem is inspired by decades of cognitive science and neuroscience research. Special thanks to the researchers whose work made this possible:

- Fergus Craik & Robert Lockhart (Levels of Processing)
- Richard Atkinson & Richard Shiffrin (Multi-Store Model)
- Hermann Ebbinghaus (Forgetting Curve)
- Robert Stickgold & Matthew Walker (Sleep Consolidation)
- James McGaugh (Emotional Memory)

---

<p align="center">
  <em>"The brain is not a vessel to be filled, but a fire to be kindled." — Plutarch</em>
</p>

<p align="center">
  <strong>Built with 🧠 for AI agents that remember like humans</strong>
</p>
