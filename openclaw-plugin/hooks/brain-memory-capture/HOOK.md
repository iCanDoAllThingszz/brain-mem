---
name: brain-memory-capture
description: "Capture user messages for later encoding"
metadata:
  openclaw:
    emoji: "📥"
    events: ["message:preprocessed"]
---

# Brain Memory Capture Hook

Captures cleaned user messages after preprocessing and stores them temporarily for the encode hook to pick up after the assistant responds.