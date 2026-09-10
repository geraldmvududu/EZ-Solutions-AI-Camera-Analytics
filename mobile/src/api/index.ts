import { apiRequest } from "./client";
import type { AlertItem, Camera, CurrentUser } from "../types";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
}

export const login = (email: string, password: string) =>
  apiRequest<TokenResponse>("/api/auth/login", { method: "POST", body: { email, password }, skipAuth: true });

export const fetchCurrentUser = () => apiRequest<CurrentUser>("/api/auth/me");

export const listCameras = () => apiRequest<Camera[]>("/api/cameras");

export const listAlerts = () => apiRequest<AlertItem[]>("/api/alerts?limit=50");

export const acknowledgeAlert = (id: string) =>
  apiRequest<AlertItem>(`/api/alerts/${id}`, { method: "PATCH", body: { status: "ACKNOWLEDGED" } });

export interface NotificationItem {
  id: string;
  alert_id: string | null;
  title: string;
  body: string;
  notification_type: string;
  is_read: boolean;
  created_at: string;
}

export const listNotifications = () => apiRequest<NotificationItem[]>("/api/notifications?limit=50");
export const markNotificationRead = (id: string) =>
  apiRequest<NotificationItem>(`/api/notifications/${id}/read`, { method: "POST" });
