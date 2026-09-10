// Empty string means "same origin" (production, behind nginx) — distinct from unset
// (local `npm run dev`, which has no .env and should default to the bare backend).
const API_URL = import.meta.env.VITE_API_URL !== undefined ? import.meta.env.VITE_API_URL : "http://localhost:8000";

const ACCESS_KEY = "ez_access_token";
const REFRESH_KEY = "ez_refresh_token";

export const tokenStore = {
  getAccess: () => localStorage.getItem(ACCESS_KEY),
  getRefresh: () => localStorage.getItem(REFRESH_KEY),
  set: (access: string, refresh: string) => {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear: () => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = tokenStore.getRefresh();
  if (!refreshToken) return false;

  const resp = await fetch(`${API_URL}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!resp.ok) {
    tokenStore.clear();
    return false;
  }
  const data = await resp.json();
  tokenStore.set(data.access_token, data.refresh_token);
  return true;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  skipAuth?: boolean;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const doFetch = async (): Promise<Response> => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (!options.skipAuth) {
      const token = tokenStore.getAccess();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    }
    return fetch(`${API_URL}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  };

  let resp = await doFetch();

  if (resp.status === 401 && !options.skipAuth) {
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
    }
    const refreshed = await refreshPromise;
    if (refreshed) {
      resp = await doFetch();
    }
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export function wsUrl(path: string): string {
  // In production, VITE_API_URL is "" (nginx proxies same-origin /api and /ws to the
  // backend), so build the WS URL from the page's own origin. In dev, VITE_API_URL is
  // an absolute http(s) origin (e.g. http://localhost:8000) — just swap the scheme.
  const base = API_URL ? API_URL.replace(/^http/, "ws") : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}`;
  const token = tokenStore.getAccess();
  return `${base}${path}?token=${encodeURIComponent(token || "")}`;
}

export { API_URL };
