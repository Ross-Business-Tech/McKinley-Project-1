export function newSessionId(): string {
  const raw = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  return raw.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
}
