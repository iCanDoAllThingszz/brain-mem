// Shared state across hooks
export const sessionMap = new Map();
export const pendingMessages = new Map();
export const PENDING_TTL_MS = 2 * 60 * 1000;

export async function postJSON(url, body, timeout = 15000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
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

export function getConfig() {
  return {
    serverUrl: process.env.BRAIN_SERVER_URL || "http://localhost:8100",
    tenantId: process.env.BRAIN_TENANT_ID || "default",
    userId: process.env.BRAIN_USER_ID || "yugo",
  };
}

export function isUserSession(sessionKey, text) {
  if (sessionKey?.includes(":cron:") || sessionKey?.includes(":subagent:")) return false;
  if (!text) return true;
  return !(
    text.includes("HEARTBEAT") ||
    text.includes("[cron:") ||
    text.includes("[Inter-session message]")
  );
}

export function getSessionId(sessionKey) {
  let sid = sessionMap.get(sessionKey);
  if (!sid) {
    sid = crypto.randomUUID();
    sessionMap.set(sessionKey, sid);
  }
  return sid;
}