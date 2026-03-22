import { getConfig, postJSON, sessionMap, pendingMessages } from "../shared";

const handler = async (event) => {
  if (event.type !== "command" || event.action !== "new") return;

  const sessionKey = event.context?.sessionKey || "default";
  if (sessionKey?.includes(":cron:") || sessionKey?.includes(":subagent:")) return;

  pendingMessages.delete(sessionKey);

  const sessionId = sessionMap.get(sessionKey);
  if (!sessionId) return;

  const cfg = getConfig();

  try {
    await postJSON(`${cfg.serverUrl}/hooks/session-end`, {
      tenant_id: cfg.tenantId,
      user_id: cfg.userId,
      session_id: sessionId,
    });
    sessionMap.delete(sessionKey);
    event.messages?.push("📝 Session summary generated");
  } catch (err) {
    console.error(`[brain-memory-session] ${err}`);
  }
};

export default handler;