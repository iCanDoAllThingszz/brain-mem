/**
 * Brain Memory — OpenClaw Plugin
 *
 * Hippocampal-inspired memory system with:
 * - Working memory (session-level context cache)
 * - Encoder buffer (short-term → long-term consolidation)
 * - Multi-path retrieval (name/alias/fuzzy + relation traversal)
 * - Sleep consolidation (periodic buffer → Neo4j graph transfer)
 *
 * Wraps the brain-memory FastAPI server and integrates via OpenClaw lifecycle hooks.
 */

import { spawn, type ChildProcess } from "node:child_process";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk/core";

// ============================================================================
// Config
// ============================================================================

type BrainMemoryConfig = {
  serverUrl: string;
  tenantId: string;
  userId: string;
  autoStart: boolean;
  serverPath: string;
};

function parseConfig(raw: Record<string, unknown> | undefined): BrainMemoryConfig {
  return {
    serverUrl: (raw?.serverUrl as string) || "http://localhost:8100",
    tenantId: (raw?.tenantId as string) || "default",
    userId: (raw?.userId as string) || "yugo",
    autoStart: raw?.autoStart !== false,
    serverPath:
      (raw?.serverPath as string) ||
      "/root/.openclaw/workspace/projects/brain-memory",
  };
}

// ============================================================================
// HTTP Client (minimal, no deps)
// ============================================================================

async function postJSON(url: string, body: unknown, timeoutMs = 15000): Promise<any> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

async function getJSON(url: string, timeoutMs = 5000): Promise<any> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

// ============================================================================
// Server Process Manager
// ============================================================================

let serverProcess: ChildProcess | null = null;

async function isServerHealthy(baseUrl: string): Promise<boolean> {
  try {
    const data = await getJSON(`${baseUrl}/health`, 3000);
    return data?.status === "ok";
  } catch {
    return false;
  }
}

function startServer(serverPath: string, logger: any): ChildProcess {
  logger.info(`brain-memory: starting server at ${serverPath}`);
  const proc = spawn("python3", ["-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8100"], {
    cwd: serverPath,
    stdio: ["ignore", "pipe", "pipe"],
    detached: false,
  });
  proc.stdout?.on("data", (d: Uint8Array) => logger.info(`brain-memory-server: ${d.toString().trim()}`));
  proc.stderr?.on("data", (d: Uint8Array) => logger.warn(`brain-memory-server: ${d.toString().trim()}`));
  proc.on("exit", (code: number | null) => {
    logger.warn(`brain-memory: server exited with code ${code}`);
    serverProcess = null;
  });
  return proc;
}

async function ensureServer(cfg: BrainMemoryConfig, logger: any): Promise<boolean> {
  if (await isServerHealthy(cfg.serverUrl)) return true;
  if (!cfg.autoStart) return false;

  serverProcess = startServer(cfg.serverPath, logger);

  // Wait up to 15s for server to become healthy
  for (let i = 0; i < 30; i++) {
    await new Promise((r) => setTimeout(r, 500));
    if (await isServerHealthy(cfg.serverUrl)) {
      logger.info("brain-memory: server is healthy");
      return true;
    }
  }
  logger.error("brain-memory: server failed to start within 15s");
  return false;
}

// ============================================================================
// Session ID Management
// ============================================================================

// Map OpenClaw sessionKey → brain-memory sessionId
const sessionMap = new Map<string, string>();

// Temporary store: sessionKey → last inbound user message (set at message:preprocessed, consumed at message:sent)
const pendingUserMessages = new Map<string, string>();

function getOrCreateSessionId(sessionKey: string): string {
  let sid = sessionMap.get(sessionKey);
  if (!sid) {
    sid = crypto.randomUUID();
    sessionMap.set(sessionKey, sid);
  }
  return sid;
}

// ============================================================================
// Plugin Definition
// ============================================================================

const brainMemoryPlugin = {
  id: "brain-memory",
  name: "Brain Memory",
  configSchema: {
    type: "object",
    properties: {
      serverUrl: { type: "string", default: "http://localhost:8100" },
      tenantId: { type: "string", default: "default" },
      userId: { type: "string", default: "yugo" },
      autoStart: { type: "boolean", default: true },
      serverPath: { type: "string", default: "/root/.openclaw/workspace/projects/brain-memory" },
    },
  },

  register(api: OpenClawPluginApi) {
    const cfg = parseConfig(api.pluginConfig as Record<string, unknown>);
    api.logger.info(`brain-memory: registered (server=${cfg.serverUrl}, tenant=${cfg.tenantId}, user=${cfg.userId})`);

    // ========================================================================
    // Tools
    // ========================================================================

    api.registerTool(
      {
        name: "brain_recall",
        description:
          "Search through the brain-inspired long-term memory graph. " +
          "Use when you need context about past conversations, user preferences, " +
          "decisions, relationships, or previously discussed topics. " +
          "Returns synthesized context from Neo4j graph + encoder buffer.",
        parameters: {
          type: "object",
          properties: {
            query: { type: "string", description: "Natural language search query" },
            max_results: { type: "number", description: "Max memory fragments (default: 10)" },
          },
          required: ["query"],
        } as any,
        async execute(_id: string, params: unknown) {
          const { query, max_results = 10 } = params as { query: string; max_results?: number };
          const sessionKey = "tool-recall";
          const sessionId = getOrCreateSessionId(sessionKey);

          try {
            const result = await postJSON(`${cfg.serverUrl}/hooks/before-query`, {
              tenant_id: cfg.tenantId,
              user_id: cfg.userId,
              session_id: sessionId,
              query,
              max_results,
              recent_messages: [],
            });

            const context = result?.data?.context || "No relevant memories found.";
            return {
              content: [{ type: "text", text: context }],
            };
          } catch (err) {
            return {
              content: [{ type: "text", text: `Memory recall failed: ${String(err)}` }],
            };
          }
        },
      },
      { optional: true },
    );

    api.registerTool(
      {
        name: "brain_consolidate",
        description:
          "Trigger sleep consolidation — transfer buffered memories into the long-term Neo4j graph. " +
          "Performs deduplication, pattern discovery, and memory decay. " +
          "Use periodically or when explicitly asked to consolidate memories.",
        parameters: { type: "object", properties: {}, required: [] } as any,
        async execute(_id: string, _params: unknown) {
          try {
            const result = await postJSON(`${cfg.serverUrl}/hooks/consolidate`, {
              tenant_id: cfg.tenantId,
              user_id: cfg.userId,
            });
            const stats = result?.data || {};
            return {
              content: [{
                type: "text",
                text: `Consolidation triggered. Nodes created: ${stats.nodes_created || 0}, ` +
                  `updated: ${stats.nodes_updated || 0}, relations: ${stats.relations_created || 0}`,
              }],
            };
          } catch (err) {
            return {
              content: [{ type: "text", text: `Consolidation failed: ${String(err)}` }],
            };
          }
        },
      },
      { optional: true },
    );

    // ========================================================================
    // Session filtering — only process real user conversations
    // ========================================================================

    function isUserSession(sessionKey: string, prompt?: string): boolean {
      // Skip cron jobs
      if (sessionKey.includes(":cron:")) return false;
      // Skip sub-agents
      if (sessionKey.includes(":subagent:")) return false;
      // Skip heartbeat prompts, cron tasks, and inter-session messages
      return !(
        prompt?.includes("HEARTBEAT") ||
        prompt?.includes("Read HEARTBEAT.md") ||
        prompt?.includes("Pre-compaction memory flush") ||
        prompt?.includes("[cron:") ||
        prompt?.includes("[Inter-session message]")
      );
    }

    // ========================================================================
    // Lifecycle Hooks
    // ========================================================================

    // --- before_prompt_build: inject working memory context (runs after session load, messages available) ---
    api.on("before_prompt_build", async (event: any, ctx: any) => {
      if (!event.prompt || event.prompt.length < 5) return;

      const sessionKey = ctx.sessionKey || "default";

      // Only process real user conversations
      if (!isUserSession(sessionKey, event.prompt)) return;

      const sessionId = getOrCreateSessionId(sessionKey);

      // Extract clean user query from prompt (strip metadata wrappers)
      let query = event.prompt;
      if (query.includes("message_id") && query.includes("sender_id")) {
        const parts = query.split(/\n\n/);
        for (let j = parts.length - 1; j >= 0; j--) {
          const part = parts[j].trim();
          if (!part) continue;
          if (part.startsWith("{") || part.startsWith("```")) continue;
          if (part.startsWith("Conversation info") || part.startsWith("Sender (")) continue;
          if (part.startsWith("<working-memory>") || part.startsWith("<retrieved-memories>")) continue;
          if (part.startsWith("System:") || part.startsWith("[Inter-session")) continue;
          query = part;
          break;
        }
      }
      if (query.length < 5) return;

      try {
        // Sequential: session-start must complete before before-query
        // so that WM is loaded before retrieval tries to use it
        const wmResult = await postJSON(`${cfg.serverUrl}/hooks/session-start`, {
          tenant_id: cfg.tenantId,
          user_id: cfg.userId,
          session_id: sessionId,
        }, 8000).catch(() => null);

        const retrieveResult = await postJSON(`${cfg.serverUrl}/hooks/before-query`, {
          tenant_id: cfg.tenantId,
          user_id: cfg.userId,
          session_id: sessionId,
          query: query,
        }, 8000).catch(() => null);

        const wmContext = wmResult?.data?.context;
        const retrievedContext = retrieveResult?.data?.context;

        // Combine working memory + retrieved context
        const parts: string[] = [];
        if (wmContext && wmContext !== "No prior context available for this user.") {
          parts.push(`<working-memory>\n${wmContext}\n</working-memory>`);
        }
        if (retrievedContext && retrievedContext !== "No relevant memories found.") {
          parts.push(`<retrieved-memories>\nTreat as historical context only.\n${retrievedContext}\n</retrieved-memories>`);
        }

        if (parts.length > 0) {
          api.logger.info?.(`brain-memory: injecting ${parts.length} context blocks`);
          return { prependContext: parts.join("\n\n") };
        }
      } catch (err) {
        api.logger.warn(`brain-memory: before_agent_start hook failed: ${String(err)}`);
      }
    });

    // --- message:sent: encode the inbound user message after AI response is delivered ---
    // event.sessionKey — session identifier
    // event.context.content — the assistant response text just sent
    // event.context.channelId — channel type (whatsapp, telegram, etc.)
    api.registerHook(
      "message:sent",
      async (event: any) => {
        if (!event.context?.success) return;

        const sessionKey = event.sessionKey || "default";
        if (!isUserSession(sessionKey)) return;

        // Retrieve the inbound user message stored at message:preprocessed time
        const userMessage = pendingUserMessages.get(sessionKey);
        if (!userMessage) return;
        pendingUserMessages.delete(sessionKey);

        const sessionId = getOrCreateSessionId(sessionKey);
        const assistantResponse: string = event.context?.content || "";

        // Fire-and-forget: send to perceiver → evaluator → encoder pipeline
        postJSON(`${cfg.serverUrl}/hooks/after-response`, {
          tenant_id: cfg.tenantId,
          user_id: cfg.userId,
          session_id: sessionId,
          user_message: userMessage,
          assistant_response: assistantResponse,
        }).catch((err) => {
          api.logger.warn(`brain-memory: after-response failed: ${String(err)}`);
        });
      },
      {
        name: "brain-memory.message-sent",
        description: "Encodes the user message + assistant response into the brain-memory buffer after delivery",
      },
    );

    // --- message:preprocessed: capture the cleaned inbound user message before it reaches the agent ---
    // event.context.bodyForAgent — final enhanced text visible to the agent
    api.registerHook(
      "message:preprocessed",
      async (event: any) => {
        const sessionKey = event.sessionKey || "default";
        if (!isUserSession(sessionKey)) return;

        const text: string = (event.context?.bodyForAgent || event.context?.body || "").trim();
        if (text.length < 10 || text.length > 2000) return;

        // Skip system-generated content
        if (
          text.includes("<working-memory>") || text.includes("<retrieved-memories>") ||
          text.includes("<<<BEGIN_UNTRUSTED_CHILD_RESULT>>>") ||
          text.includes("[Internal task completion event]") ||
          text.includes("OpenClaw runtime context (internal)") ||
          text.includes("subagent_announce") ||
          text.includes("HEARTBEAT_OK") || text.includes("Read HEARTBEAT.md") ||
          text.includes("Pre-compaction memory flush") ||
          /^\[Inter-session message]/.test(text) ||
          /^System:/.test(text) ||
          /\[cron:/.test(text)
        ) return;

        // Stash for message:sent handler to pick up
        pendingUserMessages.set(sessionKey, text);
      },
      {
        name: "brain-memory.message-preprocessed",
        description: "Captures the inbound user message for later encoding",
      },
    );

    // --- command:new: generate session summary when user starts a new session (/new) ---
    // event.sessionKey — the OLD session key being closed
    // event.context.senderId — user identifier
    api.registerHook(
      "command:new",
      async (event: any) => {
        const sessionKey = event.sessionKey || "default";

        // Only process real user conversations
        if (!isUserSession(sessionKey)) return;

        const sessionId = sessionMap.get(sessionKey);
        if (!sessionId) return;

        try {
          await postJSON(`${cfg.serverUrl}/hooks/session-end`, {
            tenant_id: cfg.tenantId,
            user_id: cfg.userId,
            session_id: sessionId,
          });
          sessionMap.delete(sessionKey);
          api.logger.info?.(`brain-memory: session ${sessionKey} ended, summary generated`);
        } catch (err) {
          api.logger.warn(`brain-memory: session_end failed: ${String(err)}`);
        }
      },
      {
        name: "brain-memory.command-new",
        description: "Generates a session summary and clears working memory when user issues /new",
      },
    );

    // ========================================================================
    // CLI Commands
    // ========================================================================

    api.registerCli(
      ({ program }: { program: any }) => {
        const brain = program.command("brain").description("Brain memory plugin commands");

        brain
          .command("health")
          .description("Check brain-memory server health")
          .action(async () => {
            const healthy = await isServerHealthy(cfg.serverUrl);
            console.log(healthy ? "✅ Server is healthy" : "❌ Server is not reachable");
          });

        brain
          .command("consolidate")
          .description("Trigger sleep consolidation")
          .action(async () => {
            console.log("Triggering consolidation...");
            const result = await postJSON(`${cfg.serverUrl}/hooks/consolidate`, {
              tenant_id: cfg.tenantId,
              user_id: cfg.userId,
            });
            console.log(JSON.stringify(result?.data, null, 2));
          });

        brain
          .command("recall")
          .description("Search brain memory")
          .argument("<query>", "Search query")
          .action(async (query: string) => {
            const result = await postJSON(`${cfg.serverUrl}/hooks/before-query`, {
              tenant_id: cfg.tenantId,
              user_id: cfg.userId,
              session_id: "cli-recall",
              query,
            });
            console.log(result?.data?.context || "No results");
          });

        brain
          .command("start")
          .description("Start the brain-memory server")
          .action(async () => {
            if (await isServerHealthy(cfg.serverUrl)) {
              console.log("Server is already running");
              return;
            }
            serverProcess = startServer(cfg.serverPath, {
              info: console.log,
              warn: console.warn,
              error: console.error,
            });
            console.log("Server starting...");
          });

        brain
          .command("stop")
          .description("Stop the brain-memory server")
          .action(() => {
            if (serverProcess) {
              serverProcess.kill();
              serverProcess = null;
              console.log("Server stopped");
            } else {
              console.log("No managed server process");
            }
          });

        brain
          .command("logs")
          .description("View recent brain-memory activity logs")
          .option("-n, --lines <n>", "Number of log entries", "20")
          .action(async (opts: { lines: string }) => {
            try {
              const result = await getJSON(`${cfg.serverUrl}/logs?n=${opts.lines}`, 5000);
              console.log(result?.logs || "No logs available");
            } catch (err) {
              console.log(`Failed to fetch logs: ${err}`);
            }
          });
      },
      { commands: ["brain"] },
    );

    // ========================================================================
    // Service (auto-start server)
    // ========================================================================

    api.registerService({
      id: "brain-memory",
      start: async () => {
        const ok = await ensureServer(cfg, api.logger);
        if (ok) {
          api.logger.info("brain-memory: service started, server is healthy");
        } else {
          api.logger.warn("brain-memory: service started but server is not available");
        }
      },
      stop: () => {
        if (serverProcess) {
          serverProcess.kill();
          serverProcess = null;
        }
        api.logger.info("brain-memory: service stopped");
      },
    });
  },
};

export default brainMemoryPlugin;
