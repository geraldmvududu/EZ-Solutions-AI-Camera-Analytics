import AsyncStorage from "@react-native-async-storage/async-storage";

// Android emulator alias for host localhost by default; override with EXPO_PUBLIC_API_URL
// for a physical device on the lab network (see mobile/.env.example) — never hard-coded
// past this single fallback (section 41).
const API_URL = process.env.EXPO_PUBLIC_API_URL || "http://10.0.2.2:8000";

const ACCESS_KEY = "ez_mobile_access_token";
const REFRESH_KEY = "ez_mobile_refresh_token";

export const tokenStore = {
  getAccess: () => AsyncStorage.getItem(ACCESS_KEY),
  getRefresh: () => AsyncStorage.getItem(REFRESH_KEY),
  set: async (access: string, refresh: string) => {
    await AsyncStorage.multiSet([[ACCESS_KEY, access], [REFRESH_KEY, refresh]]);
  },
  clear: () => AsyncStorage.multiRemove([ACCESS_KEY, REFRESH_KEY]),
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
  const refreshToken = await tokenStore.getRefresh();
  if (!refreshToken) return false;

  const resp = await fetch(`${API_URL}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!resp.ok) {
    await tokenStore.clear();
    return false;
  }
  const data = await resp.json();
  await tokenStore.set(data.access_token, data.refresh_token);
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
      const token = await tokenStore.getAccess();
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
    if (await refreshPromise) resp = await doFetch();
  }

  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* no JSON body */
    }
    throw new ApiError(resp.status, detail);
  }

  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

export async function getStreamUrl(cameraId: string): Promise<string> {
  const token = (await tokenStore.getAccess()) || "";
  return `${API_URL}/api/cameras/${cameraId}/stream?token=${encodeURIComponent(token)}`;
}

export { API_URL };
