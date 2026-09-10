import { apiRequest } from "./client";
import type { AlertItem, EventItem } from "../types";

export const listEvents = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return apiRequest<EventItem[]>(`/api/events${qs ? `?${qs}` : ""}`);
};

export const listAlerts = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return apiRequest<AlertItem[]>(`/api/alerts${qs ? `?${qs}` : ""}`);
};

export const updateAlert = (id: string, payload: { status?: string; notes?: string; assigned_user_id?: string }) =>
  apiRequest<AlertItem>(`/api/alerts/${id}`, { method: "PATCH", body: payload });
