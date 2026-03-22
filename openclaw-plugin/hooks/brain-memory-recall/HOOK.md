---
name: brain-memory-recall
description: "Inject working memory and retrieved context before agent query"
metadata:
  openclaw:
    emoji: "🧠"
    events: ["message:preprocessed"]
---

# Brain Memory Recall Hook

Retrieves relevant memories from the brain-memory system and injects them as context before the agent processes the user query.

Combines:
- Working memory (session-level context cache)
- Long-term memory (Neo4j graph retrieval)