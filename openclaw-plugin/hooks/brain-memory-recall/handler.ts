import { getConfig, getSessionId, isUserSession, postJSON } from "../shared";

const handler = async (event) => {
  if (event.type !== "message" || event.action !== "preprocessed") return;

  const sessionKey = event.context?.sessionKey || "default";
  const text = event.context?.bodyForAgent || event.context?.body || "";

  if (!isUserSession(sessionKey, text) || text.length < 5) return;

  const cfg = getConfig();
  const sessionId = getSessionId(sessionKey);

  try {
    const [wmResult, retrieveResult] = await Promise.all([
      postJSON(`${cfg.serverUrl}/hooks/session-start`, {
        tenant_id: cfg.tenantId,
        user_id: cfg.userId,
        session_id: sessionId,
      }, 8000).catch(() => null),
      postJSON(`${cfg.serverUrl}/hooks/before-query`, {
        tenant_id: cfg.tenantId,
        user_id: cfg.userId,
        session_id: sessionId,
        query: text,
      }, 8000).catch(() => null),
    ]);

    const parts = [];
    const wmContext = wmResult?.data?.context;
    const retrievedContext = retrieveResult?.data?.context;

    if (wmContext && wmContext !== "No prior context available for this user.") {
      parts.push(`<working-memory>\n${wmContext}\n</working-memory>`);
    }
    if (retrievedContext && retrievedContext !== "No relevant memories found.") {
      parts.push(`<retrieved-memories>\n${retrievedContext}\n</retrieved-memories>`);
    }

    if (parts.length > 0) {
      event.context.bodyForAgent = `${parts.join("\n\n")}\n\n${text}`;
      event.messages?.push("🧠 Memory context injected");
    }
  } catch (err) {
    console.error(`[brain-memory-recall] ${err}`);
  }
};

export default handler;