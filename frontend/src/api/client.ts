/** Typed API client with JWT attach + one-shot refresh-and-retry on 401. */

const BASE = "/api/v1";
const TOKENS_KEY = "swingtrade.tokens";

interface Tokens {
  access_token: string;
  refresh_token: string;
}

export function getTokens(): Tokens | null {
  try {
    const raw = localStorage.getItem(TOKENS_KEY);
    return raw ? (JSON.parse(raw) as Tokens) : null;
  } catch {
    return null;
  }
}

export function setTokens(tokens: Tokens | null): void {
  if (tokens) localStorage.setItem(TOKENS_KEY, JSON.stringify(tokens));
  else localStorage.removeItem(TOKENS_KEY);
  window.dispatchEvent(new Event("swingtrade-auth"));
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function refreshTokens(): Promise<boolean> {
  const tokens = getTokens();
  if (!tokens) return false;
  const resp = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
  if (!resp.ok) {
    setTokens(null);
    return false;
  }
  setTokens((await resp.json()) as Tokens);
  return true;
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; params?: Record<string, unknown> } = {},
  retried = false,
): Promise<T> {
  const url = new URL(BASE + path, window.location.origin);
  for (const [k, v] of Object.entries(options.params ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const tokens = getTokens();
  if (tokens) headers["Authorization"] = `Bearer ${tokens.access_token}`;

  const resp = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (resp.status === 401 && tokens && !retried && (await refreshTokens())) {
    return api<T>(path, options, true);
  }
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

export const isLoggedIn = () => getTokens() !== null;
