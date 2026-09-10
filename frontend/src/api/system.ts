import { apiRequest } from "./client";
import type { DashboardStats, SystemHealth, UserItem } from "../types";

export const getDashboardStats = () => apiRequest<DashboardStats>("/api/system/dashboard-stats");
export const getSystemHealth = () => apiRequest<SystemHealth>("/api/system/health");

export const listUsers = () => apiRequest<UserItem[]>("/api/users");
export const createUser = (payload: { email: string; password: string; full_name: string; role: string }) =>
  apiRequest<UserItem>("/api/users", { method: "POST", body: payload });
export const updateUser = (id: string, payload: Partial<{ full_name: string; role: string; is_active: boolean; password: string }>) =>
  apiRequest<UserItem>(`/api/users/${id}`, { method: "PATCH", body: payload });
export const deleteUser = (id: string) => apiRequest<void>(`/api/users/${id}`, { method: "DELETE" });

export interface AuditLogEntry {
  id: string;
  user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string;
  ip_address: string;
  result: string;
  details: Record<string, unknown>;
  created_at: string;
}

export const listAuditLogs = () => apiRequest<AuditLogEntry[]>("/api/audit-logs");
