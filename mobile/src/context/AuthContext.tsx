import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import * as api from "../api";
import { tokenStore } from "../api/client";
import { registerForPushNotifications, unregisterPushToken } from "../push";
import type { CurrentUser } from "../types";

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [pushToken, setPushToken] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const token = await tokenStore.getAccess();
      if (token) {
        try {
          setUser(await api.fetchCurrentUser());
          registerForPushNotifications().then(setPushToken);
        } catch {
          await tokenStore.clear();
        }
      }
      setLoading(false);
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await api.login(email, password);
    await tokenStore.set(tokens.access_token, tokens.refresh_token);
    setUser(await api.fetchCurrentUser());
    registerForPushNotifications().then(setPushToken);
  }, []);

  const logout = useCallback(async () => {
    if (pushToken) await unregisterPushToken(pushToken);
    await tokenStore.clear();
    setUser(null);
    setPushToken(null);
  }, [pushToken]);

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
