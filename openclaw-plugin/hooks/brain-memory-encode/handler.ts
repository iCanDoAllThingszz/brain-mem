import { getConfig, getSessionId, isUserSession, postJSON, pendingMessages, PENDING_TTL_MS } from "../shared";

const handler = async (event) => {
  if (event.type !== "message" || event.action !== "sent") return;
  if (!event.context?.success) return;

  const sessionKey = event.context?.sessionKey || "default";
  if (!isUserSession(sessionKey)) return;

  const userMessage = pendingMessages.get(sessionKey);
  if (!userMessage) return;

  const now = Date.now();
  if (now - userMessage.ts > PENDING_TTL_MS) {
    pendingMessages.delete(sessionKey);
    return;
  }

  pendingMessages.delete(sessionKey);

  const cfg = getConfig();
  const sessionId = getSessionId(sessionKey);
  const assistantResponse = event.context?.content || "";

  postJSON(`${cfg.serverUrl}/hooks/after-response`, {
    tenant_id: cfg.tenantId,
    user_id: cfg.userId,
    session_id: sessionId,
    user_message: userMessage.text,
    assistant_response: assistantResponse,
  }).catch((err) => console.error(`[brain-memory-encode] ${err}`));
};

export default handler;