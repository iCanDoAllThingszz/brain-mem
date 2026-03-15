# OpenClaw Integration Guide

This guide explains how to integrate Brain Memory Service with OpenClaw as a context-engine plugin.

## Overview

The Brain Memory plugin enhances OpenClaw's conversational capabilities by:
- Retrieving relevant long-term memories before each query
- Encoding user messages into structured memory graphs
- Providing persistent memory across sessions
- Supporting prospective memory (reminders and scheduled actions)

**Important**: This plugin does NOT replace OpenClaw's built-in conversation history. It augments the agent's context with long-term memories stored in the Brain Memory Service.

## Prerequisites

1. **Brain Memory Service Running**
   - The service must be accessible at a URL (e.g., `http://localhost:8100`)
   - Neo4j database must be running and connected
   - Verify health: `curl http://localhost:8100/health`

2. **OpenClaw Installed**
   - OpenClaw CLI or desktop application
   - Extensions directory: `~/.openclaw/extensions/`

## Plugin Installation

### 1. Create Plugin Directory

```bash
mkdir -p ~/.openclaw/extensions/brain-memory
cd ~/.openclaw/extensions/brain-memory
```

### 2. Create Plugin Manifest

Create `openclaw.plugin.json`:

```json
{
  "name": "brain-memory",
  "version": "0.1.0",
  "type": "context-engine",
  "description": "Long-term memory system powered by Brain Memory Service",
  "author": "Brain Memory Team",
  "entry": "index.ts",
  "config": {
    "serverUrl": {
      "type": "string",
      "default": "http://localhost:8100",
      "description": "Brain Memory Service URL"
    },
    "tenantId": {
      "type": "string",
      "default": "openclaw",
      "description": "Tenant identifier for multi-tenancy"
    },
    "userId": {
      "type": "string",
      "required": true,
      "description": "User identifier (must be unique per user)"
    },
    "autoStart": {
      "type": "boolean",
      "default": true,
      "description": "Automatically start memory session with each conversation"
    }
  }
}
```

### 3. Create Plugin Implementation

Create `index.ts`:

```typescript
import { Plugin, ContextEngine, Message } from '@openclaw/sdk';

interface BrainMemoryConfig {
  serverUrl: string;
  tenantId: string;
  userId: string;
  autoStart: boolean;
}

interface SessionContext {
  sessionId: string;
  tenantId: string;
  userId: string;
}

export default class BrainMemoryPlugin implements Plugin, ContextEngine {
  private config: BrainMemoryConfig;
  private sessionContext: SessionContext | null = null;

  constructor(config: BrainMemoryConfig) {
    this.config = config;
  }

  async initialize(): Promise<void> {
    // Verify service is reachable
    try {
      const response = await fetch(`${this.config.serverUrl}/health`);
      if (!response.ok) {
        throw new Error(`Health check failed: ${response.status}`);
      }
      console.log('[BrainMemory] Service connected successfully');
    } catch (error) {
      console.error('[BrainMemory] Failed to connect to service:', error);
      throw error;
    }
  }

  async before_agent_start(context: any): Promise<any> {
    if (!this.config.autoStart) {
      return context;
    }

    // Generate session ID
    const sessionId = this.generateSessionId();
    this.sessionContext = {
      sessionId,
      tenantId: this.config.tenantId,
      userId: this.config.userId,
    };

    try {
      // Call session-start hook
      const response = await fetch(`${this.config.serverUrl}/hooks/session-start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: this.sessionContext.tenantId,
          user_id: this.sessionContext.userId,
          session_id: this.sessionContext.sessionId,
          user_profile: context.user_profile || {},
          agent_context: context.agent_context || {},
        }),
      });

      const result = await response.json();
      if (result.code === 0) {
        const data = result.data;

        // Inject retrieved memories into context
        if (data.context) {
          context.retrieved_memories = data.context;
        }

        // Inject pending reminders
        if (data.pending_reminders && data.pending_reminders.length > 0) {
          context.pending_reminders = data.pending_reminders;
        }

        console.log('[BrainMemory] Session started:', sessionId);
      } else {
        console.error('[BrainMemory] Session start failed:', result.message);
      }
    } catch (error) {
      console.error('[BrainMemory] Session start error:', error);
    }

    return context;
  }

  async before_query(query: string, context: any): Promise<any> {
    if (!this.sessionContext) {
      return context;
    }

    try {
      // Retrieve relevant memories for this query
      const response = await fetch(`${this.config.serverUrl}/hooks/before-query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: this.sessionContext.tenantId,
          user_id: this.sessionContext.userId,
          session_id: this.sessionContext.sessionId,
          query: query,
          recent_messages: context.recent_messages || [],
        }),
      });

      const result = await response.json();
      if (result.code === 0) {
        const data = result.data;

        // Inject retrieved context
        if (data.context) {
          context.retrieved_memories = data.context;
        }

        console.log('[BrainMemory] Retrieved memories for query');
      }
    } catch (error) {
      console.error('[BrainMemory] Memory retrieval error:', error);
    }

    return context;
  }

  async after_response(userMessage: string, assistantResponse: string): Promise<void> {
    if (!this.sessionContext) {
      return;
    }

    try {
      // Encode user message into memory (background task)
      await fetch(`${this.config.serverUrl}/hooks/after-response`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: this.sessionContext.tenantId,
          user_id: this.sessionContext.userId,
          session_id: this.sessionContext.sessionId,
          user_message: userMessage,
          assistant_response: assistantResponse,
        }),
      });

      console.log('[BrainMemory] Message encoding queued');
    } catch (error) {
      console.error('[BrainMemory] Encoding error:', error);
    }
  }

  async on_session_end(conversationHistory: Message[]): Promise<void> {
    if (!this.sessionContext) {
      return;
    }

    try {
      // Generate session summary
      await fetch(`${this.config.serverUrl}/hooks/session-end`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: this.sessionContext.tenantId,
          user_id: this.sessionContext.userId,
          session_id: this.sessionContext.sessionId,
          conversation_history: conversationHistory,
        }),
      });

      console.log('[BrainMemory] Session ended:', this.sessionContext.sessionId);
      this.sessionContext = null;
    } catch (error) {
      console.error('[BrainMemory] Session end error:', error);
    }
  }

  private generateSessionId(): string {
    return `openclaw-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }
}
```

## Configuration

### Plugin Settings

Configure the plugin in OpenClaw's settings or via CLI:

```bash
openclaw plugin config brain-memory \
  --serverUrl "http://localhost:8100" \
  --tenantId "openclaw" \
  --userId "your-user-id" \
  --autoStart true
```

### Docker Compose Setup

If running Brain Memory Service via docker-compose, ensure the service is accessible from OpenClaw:

```yaml
# docker-compose.yml
services:
  brain-mem:
    ports:
      - "8100:8100"  # Expose to host
```

## Verification

### 1. Check Plugin Status

```bash
openclaw plugin list
```

You should see `brain-memory` in the active plugins list.

### 2. Test Integration

Start a conversation in OpenClaw:

```
User: I'm working on a project called brain-memory
Agent: [Response with context]

User: What am I working on?
Agent: [Should recall the brain-memory project from memory]
```

### 3. View Activity Logs

Check Brain Memory Service logs:

```bash
curl http://localhost:8100/logs
```

You should see entries for:
- `hook_session_start`
- `hook_before_query`
- `perceiver`
- `evaluator`
- `encoder`

## API Endpoints Used

The plugin interacts with these Brain Memory Service endpoints:

| Endpoint | Purpose | When Called |
|----------|---------|-------------|
| `POST /hooks/session-start` | Initialize session, load working memory | `before_agent_start` |
| `POST /hooks/before-query` | Retrieve relevant memories | `before_query` |
| `POST /hooks/after-response` | Encode user message | `after_response` |
| `POST /hooks/session-end` | Generate session summary | `on_session_end` |

## Advanced Features

### Prospective Memory (Reminders)

Users can set reminders:

```
User: Remind me to review the code tomorrow at 2pm
```

The Brain Memory Service will:
1. Detect this as a prospective memory
2. Store the trigger (time-based: tomorrow 2pm)
3. Inject the reminder at the appropriate time

### Memory Consolidation

Trigger background consolidation to merge and organize memories:

```bash
curl -X POST http://localhost:8100/hooks/consolidate \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"openclaw","user_id":"your-user-id"}'
```

### Multi-User Support

Each user should have a unique `userId` in the plugin configuration. The Brain Memory Service isolates memories by `tenant_id` and `user_id`.

## Troubleshooting

### Plugin Not Loading

- Check plugin directory: `~/.openclaw/extensions/brain-memory/`
- Verify `openclaw.plugin.json` is valid JSON
- Check OpenClaw logs for plugin errors

### Service Connection Failed

- Verify service is running: `curl http://localhost:8100/health`
- Check `serverUrl` in plugin config
- Ensure firewall allows connections to port 8100

### No Memories Retrieved

- Memories need time to encode (background task)
- Check activity logs: `curl http://localhost:8100/logs`
- Verify `tenant_id` and `user_id` match between sessions

### Memory Quality Issues

- Ensure LLM is properly configured in `config.yaml`
- Check that `api_key` is valid
- Review perceiver/evaluator logs for classification issues

## Best Practices

1. **Unique User IDs**: Use stable, unique identifiers for each user
2. **Session Management**: Let the plugin handle session lifecycle automatically
3. **Error Handling**: The plugin gracefully degrades if the service is unavailable
4. **Privacy**: Memories are isolated by tenant and user - ensure proper access control
5. **Performance**: Memory retrieval is fast (<100ms typical), but encoding happens in background

## Support

For issues or questions:
- Brain Memory Service: https://github.com/your-repo/brain-memory
- OpenClaw: https://openclaw.ai/docs
