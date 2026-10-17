export const API_BASE = "/api";

let authToken = "role:PLANNER";

export function setAuth(token: string) {
  authToken = token;
}

async function request(path: string, opts: RequestInit = {}) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...(opts.headers as Record<string, string>),
  };
  const res = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers,
  } as any);
  if (!res.ok) {
    let detail = "";
    try { detail = (await res.json()).detail || res.statusText; } catch { detail = res.statusText; }
    throw new Error(`${res.status} ${detail}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get: (p: string) => request(p),
  post: (p: string, body?: any) => request(p, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  sse: (p: string) => new EventSource(`${API_BASE}${p}`),
};
