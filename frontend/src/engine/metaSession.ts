/**
 * The browser's session id for the Meta-calling routes. A server with spend
 * limits (THEARTIST_META_LIMITS, or a public host) admits those requests per
 * X-TheArtist-Session, so every Meta request sends the same id: created once
 * and kept in localStorage, or one per page load when storage is unavailable.
 *
 * No other imports, so `node --test` loads it directly.
 */
const STORAGE_KEY = 'theartist-meta-session';
export const SESSION_HEADER = 'X-TheArtist-Session';
/** The server refuses longer ids (limits.MAX_SESSION_CHARS). */
const MAX_SESSION_CHARS = 128;

let pageSession: string | null = null;

function newSessionId(): string {
  // randomUUID exists only in secure contexts; a plain-http host still has getRandomValues
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

/** The stored id, created on first use; a per-page-load id when storage throws. */
export function metaSessionId(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && stored.length <= MAX_SESSION_CHARS) return stored;
    const id = newSessionId();
    localStorage.setItem(STORAGE_KEY, id);
    return id;
  } catch {
    pageSession ??= newSessionId();
    return pageSession;
  }
}

/** Headers every Meta-calling request carries. */
export function metaHeaders(): Record<string, string> {
  return { [SESSION_HEADER]: metaSessionId() };
}
