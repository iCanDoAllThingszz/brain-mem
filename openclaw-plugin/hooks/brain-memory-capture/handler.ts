import { isUserSession, pendingMessages } from "../shared";

const handler = async (event) => {
  if (event.type !== "message" || event.action !== "preprocessed") return;

  const sessionKey = event.context?.sessionKey || "default";
  const text = (event.context?.bodyForAgent || event.context?.body || "").trim();

  if (!isUserSession(sessionKey, text) || text.length < 10 || text.length > 2000) return;

  pendingMessages.set(sessionKey, { text, ts: Date.now() });

  // Cleanup stale entries
  if (pendingMessages.size > 20) {
    const cutoff = Date.now() - 120000;
    for (const [key, val] of pendingMessages) {
      if (val.ts < cutoff) pendingMessages.delete(key);
    }
  }
};

export default handler;