import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import * as authApi from "../api/auth";
import { tokenStore } from "../api/client";
import type { CurrentUser } from "../types";

interface AuthContextValue {
  user: CurrentUser | null;
  loading: boolean;
  login: (email: string, password: string, rememberMe: boolean) => Promise<void>;
  logout: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function restore() {
      if (tokenStore.getAccess()) {
        try {
          const me = await authApi.fetchCurrentUser();
          setUser(me);
        } catch {
          tokenStore.clear();
        }
      }
      setLoading(false);
    }
    restore();
  }, []);

  const login = useCallback(async (email: string, password: string, rememberMe: boolean) => {
    const tokens = await authApi.login(email, password, rememberMe);
    tokenStore.set(tokens.access_token, tokens.refresh_token);
    const me = await authApi.fetchCurrentUser();
    setUser(me);
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = tokenStore.getRefresh();
    tokenStore.clear();
    setUser(null);
    if (refreshToken) {
      try {
        await authApi.logout(refreshToken);
      } catch {
        /* best-effort server-side session revocation */
      }
    }
  }, []);

  const hasPermission = useCallback((permission: string) => !!user?.permissions.includes(permission), [user]);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasPermission }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
