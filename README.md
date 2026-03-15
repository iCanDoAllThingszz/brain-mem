<div align="center">

# 🧠 Brain-Mem

**Cognitive Science-Inspired Memory System for AI Agents**

*Not just storage — a brain that encodes, forgets, dreams, and grows.*

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Neo4j 5.x](https://img.shields.io/badge/Neo4j-5.x-008CC1.svg)](https://neo4j.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com)

**English** | [中文](README_CN.md)

</div>

---

## Why Brain-Mem?

Most AI memory systems are glorified key-value stores. They save everything, retrieve by keyword, and call it a day.

Human memory doesn't work that way. We **selectively encode** what matters, **emotionally weight** experiences, **consolidate during sleep**, **naturally forget** the unimportant, and **creatively recombine** fragments into new insights.

Brain-Mem brings these cognitive science principles to AI agents:

| Capability | Cognitive Basis | What it does |
|:-----------|:---------------|:-------------|
| Selective Encoding | Hippocampal gating | Only encodes novel, relevant information — noise is discarded |
| Emotional Resonance | Mood-congruent recall | Sad context? Retrieves empathetic memories + encouraging ones |
| Sleep Consolidation | Memory consolidation | Nightly cron deduplicates, discovers patterns, generates insights |
| Natural Forgetting | Ebbinghaus curve | Unimportant memories decay; important ones persist via spaced repetition |
| Reconsolidation | Memory updating | "Actually that went well" → corrects the stored memory in-place |
| Prospective Memory | Future intentions | Time/event triggers: "remind me about X when we discuss Y" |
| Creative Recombination | REM dreaming | Random memory fragments combined → occasional novel insights |
| Vector Retrieval | Semantic similarity | Hybrid graph traversal + vector search for robust recall |

## Architecture

```
User Message
     │
     ▼
┌──────────┐    ┌──────────┐    ┌──────────┐
│Perceiver │───▶│Evaluator │───▶│ Encoder  │
│(Thalamus)│    │(Cortex)  │    │(Hippocam)│
└──────────┘    └──────────┘    └────┬─────┘
 classify &      score novelty       │ entities + relations
 rewrite         & relevance         │
                                     ▼
                              ┌─────────────┐    nightly    ┌─────────────┐
                              │   Buffer    │──────────────▶│Consolidator │
                              │  (SQLite)   │               │  (Sleep)    │
                              └─────────────┘               └──────┬──────┘
                                     ▲                             │
                                     │                             ▼
                              ┌─────────────┐               ┌─────────────┐
                              │  Retriever  │◀─────────────▶│  Neo4j      │
                              │ (Multi-path)│  graph + vec  │  (LTM)      │
                              └─────────────┘               └─────────────┘
```

**Core Pipeline:** Perceiver → Evaluator → Encoder → Buffer → Consolidator → Graph

**Retrieval:** 5-path strategy (exact → alias → fuzzy → dormant → vector semantic)

**Storage:** Layered by information type:

| Input | Category | Storage |
|:------|:---------|:--------|
| "I decided to quit my job" | `cognition` | Knowledge Graph (entities + relations) |
| "Lunch: salad, 300 kcal" | `log_diet` | Markdown file + buffer index |
| "Ran 5km today" | `log_exercise` | Markdown file + buffer index |
| "Actually, the interview went great" | `reconsolidation` | Graph update (corrects existing node) |
| "Remind me about X tomorrow" | `prospective` | Graph (trigger node) |
| "Forget this person" | `forget` | Graph (node suppressed, never retrieved) |
| "hmm" / "ok" | `noise` | Discarded |

## Quick Start

### Option A: Docker Compose (Recommended)

The fastest way to get running — one command starts everything:

```bash
git clone https://github.com/iCanDoAllThingszz/brain-mem.git
cd brain-mem
cp config.yaml.example config.yaml
# Edit config.yaml with your LLM API key
docker compose up -d
```

That's it. Neo4j + Brain-Mem are running. Try the demo:

```bash
pip install httpx
python demo.py
```

### Option B: Manual Setup

#### Prerequisites

- Python 3.11+
- Neo4j 5.x
- Any OpenAI-compatible LLM API

```bash
git clone https://github.com/iCanDoAllThingszz/brain-mem.git
cd brain-mem
pip install -r requirements.txt

# Start Neo4j
docker run -d --name neo4j-memory \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/your-password \
  neo4j:5

# Configure
cp config.yaml.example config.yaml
# Edit config.yaml with your Neo4j password and LLM API key

# Run
python -m uvicorn server.app:app --host 0.0.0.0 --port 8100
```

### Setup Nightly Consolidation

```bash
# Run consolidation daily at 1:00 AM
(crontab -l 2>/dev/null; echo "0 1 * * * curl -s -X POST http://localhost:8100/hooks/consolidate \
  -H 'Content-Type: application/json' \
  -d '{\"tenant_id\":\"default\",\"user_id\":\"your-user\"}'") | crontab -
```

### Run the Demo

`demo.py` walks through the full pipeline — encoding different message types and retrieving memories:

```bash
python demo.py --base-url http://localhost:8100
```

## API Reference

### Hooks (Integration Points)

| Method | Endpoint | Description |
|:-------|:---------|:------------|
| `POST` | `/hooks/session-start` | Initialize working memory for a session |
| `POST` | `/hooks/before-query` | Retrieve relevant memories before LLM call |
| `POST` | `/hooks/after-response` | Encode user message into memory |
| `POST` | `/hooks/session-end` | Cleanup session state |
| `POST` | `/hooks/consolidate` | Trigger sleep consolidation cycle |
| `POST` | `/hooks/check-prospective` | Check time/event-based memory triggers |
| `POST` | `/hooks/backfill-embeddings` | One-time: generate embeddings for existing nodes |

### Health & Monitoring

| Method | Endpoint | Description |
|:-------|:---------|:------------|
| `GET` | `/health` | Service health check |
| `GET` | `/logs?n=30` | Recent activity logs |

### Example: Encode + Retrieve

```python
import httpx

BASE = "http://localhost:8100"
CTX = {"tenant_id": "default", "user_id": "alice", "session_id": "s1"}

# Encode a message
httpx.post(f"{BASE}/hooks/after-response", json={
    **CTX,
    "user_message": "I'm interviewing at Google next Tuesday",
    "assistant_response": "Good luck! Want me to help you prepare?"
})

# Retrieve memories
resp = httpx.post(f"{BASE}/hooks/before-query", json={
    **CTX,
    "query": "What interviews do I have coming up?"
})
print(resp.json()["data"]["context"])
# → "alice has an upcoming interview at Google scheduled for next Tuesday."
```

## Memory Decay Model

Inspired by the Ebbinghaus forgetting curve, memories decay at different rates based on type and importance:

```
effective_half_life = base_days × (1 + importance/10) × zone_factor

Zone factors:
  episodic   = 0.5   (events fade fast)
  semantic   = 2.0   (facts persist)
  procedural = 3.0   (skills last longest)
  emotional  = 1.0   (baseline)
```

## Vector Retrieval

Brain-Mem uses hybrid retrieval combining graph traversal with vector similarity search:

- **Neo4j Vector Index**: Native vector index on `MemoryNode.embedding` (1536-dim, cosine similarity)
- **Buffer Vector Search**: NumPy brute-force cosine on short-term buffer (optimal for <1000 items)
- **Embedding**: Any OpenAI-compatible embedding API

Vector search acts as a semantic fallback when exact/fuzzy matching misses — catching queries like "that AI friend" when the node is named "张三" with summary "works on LLMs at ByteDance".

## Project Structure

```
brain-mem/
├── server/
│   ├── app.py                     # FastAPI application + hook routing
│   ├── engine/
│   │   ├── perceiver.py           # Thalamus — classify & rewrite input
│   │   ├── evaluator.py           # Prefrontal cortex — score & gate
│   │   ├── encoder.py             # Hippocampus — extract entities & encode
│   │   ├── retriever.py           # Multi-path recall + vector search
│   │   ├── consolidator.py        # Sleep cycle — consolidate & dream
│   │   ├── working_memory.py      # Session context (goals, emotions)
│   │   ├── embedding_client.py    # Embedding API client with LRU cache
│   │   ├── log_writer.py          # Layered file logger + graph index
│   │   ├── prospective_checker.py # Time/event trigger checker
│   │   └── llm_client.py         # LLM API client
│   ├── storage/
│   │   ├── graph.py               # Neo4j operations + vector index
│   │   ├── buffer.py              # SQLite buffer + embedding storage
│   │   └── tag_dict.py            # Tag taxonomy
│   └── models/
│       ├── node.py                # MemoryNode schema
│       └── relation.py            # Relation schema
├── benchmark/
│   ├── run_benchmark.py           # Automated test suite
│   └── RESULTS.md                 # Latest benchmark results
├── docs/
│   ├── V3-DESIGN.md               # Detailed architecture design
│   └── openclaw-integration.md    # OpenClaw plugin guide
├── Dockerfile                     # Container image
├── docker-compose.yml             # One-command deployment
├── demo.py                        # Interactive demo script
├── config.yaml.example            # Configuration template
└── requirements.txt
```

## OpenClaw Integration

Brain-Mem works as a [context-engine plugin](https://docs.openclaw.ai) for [OpenClaw](https://github.com/openclaw/openclaw), injecting long-term memory context into agent conversations:

- **before_agent_start**: Retrieves relevant memories and injects them as `<retrieved-memories>` context
- **after_response**: Encodes the user's message into the memory pipeline
- **session lifecycle**: Manages working memory across sessions

Brain-Mem augments (not replaces) OpenClaw's built-in conversation history — it provides cross-session, long-term context that session history alone can't.

See [docs/openclaw-integration.md](docs/openclaw-integration.md) for the full setup guide.

## Benchmark

Run the built-in benchmark suite to validate all memory features:

```bash
python benchmark/run_benchmark.py --base-url http://localhost:8100
```

Latest results ([full report](benchmark/RESULTS.md)):

| Dimension | Description | Status |
|:----------|:-----------|:------:|
| Selective Encoding | Noise discarded, cognition encoded | ✅ |
| Vector Semantic Recall | Fuzzy queries find correct nodes | ✅ |
| Noise Filtering | Meaningless messages never stored | ✅ |
| Classification Routing | Messages routed to correct category | ✅ |
| Reconsolidation | Corrections update existing memories | ✅ |
| Prospective Memory | Time/event triggers fire correctly | ✅ |

## Comparison with Other Approaches

| Feature | Brain-Mem | Simple RAG | Mem0 | Letta/MemGPT |
|:--------|:---------:|:----------:|:----:|:------------:|
| Selective encoding (not everything) | ✅ | ❌ | ✅ | ✅ |
| Knowledge graph storage | ✅ | ❌ | ✅ | ❌ |
| Vector semantic search | ✅ | ✅ | ✅ | ✅ |
| Emotional resonance | ✅ | ❌ | ❌ | ❌ |
| Sleep consolidation | ✅ | ❌ | ❌ | ❌ |
| Natural forgetting (decay) | ✅ | ❌ | ❌ | ❌ |
| Memory reconsolidation | ✅ | ❌ | ❌ | ❌ |
| Prospective memory (triggers) | ✅ | ❌ | ❌ | ❌ |
| Creative recombination | ✅ | ❌ | ❌ | ❌ |
| Spaced repetition | ✅ | ❌ | ❌ | ❌ |
| Layered storage routing | ✅ | ❌ | ❌ | ✅ |
| Self-hosted / no vendor lock-in | ✅ | ✅ | ⚠️ | ✅ |

## Roadmap

- [ ] Plugin SDK for custom perceiver/encoder rules
- [ ] Multi-agent shared memory with access control
- [ ] Web dashboard for memory visualization
- [ ] Benchmark suite against LOCOMO and other memory benchmarks
- [ ] First-class support for more LLM providers

## Contributing

Contributions welcome! Please open an issue first to discuss what you'd like to change.

## License

[MIT](LICENSE)

---

<div align="center">

*"Memory is not a recording of the past, but a reconstruction in the present."*
— Daniel Schacter, *The Seven Sins of Memory*

</div>
