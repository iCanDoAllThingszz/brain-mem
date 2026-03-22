---
name: brain-memory-encode
description: "Encode user message and assistant response into memory buffer"
metadata:
  openclaw:
    emoji: "💾"
    events: ["message:sent"]
---

# Brain Memory Encode Hook

Captures user messages and assistant responses, then encodes them into the brain-memory buffer for later consolidation into long-term storage.