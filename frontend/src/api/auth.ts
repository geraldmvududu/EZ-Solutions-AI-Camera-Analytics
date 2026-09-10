import { apiRequest } from "./client";
import type { CurrentUser } from "../types";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export function login(email: string, password: string, rememberMe: boolean) {
  return apiRequest<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: { email, password, remember_me: rememberMe },
    skipAuth: true,
  });
}

export function fetchCurrentUser() {
  return apiRequest<CurrentUser>("/api/auth/me");
}

export function logout(refreshToken: string) {
  return apiRequest("/api/auth/logout", { method: "POST", body: { refresh_token: refreshToken } });
}
