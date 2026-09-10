import { apiRequest } from "./client";

export interface Recording {
  id: string;
  camera_id: string;
  file_path: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  trigger_type: string;
  is_protected: boolean;
  created_at: string;
}

export const listRecordings = () => apiRequest<Recording[]>("/api/recordings");

export interface AIRule {
  id: string;
  name: string;
  description: string;
  is_enabled: boolean;
  conditions: Record<string, unknown>;
  action_severity: string;
  action_alert_type: string;
  camera_id: string | null;
}

export const listRules = () => apiRequest<AIRule[]>("/api/rules");
export const createRule = (payload: Partial<AIRule> & { name: string; conditions: Record<string, unknown> }) =>
  apiRequest<AIRule>("/api/rules", { method: "POST", body: payload });
export const deleteRule = (id: string) => apiRequest<void>(`/api/rules/${id}`, { method: "DELETE" });

export interface Incident {
  id: string;
  title: string;
  description: string;
  severity: string;
  status: string;
  created_at: string;
}

export const listIncidents = () => apiRequest<Incident[]>("/api/incidents");
export const createIncident = (payload: { title: string; description?: string; severity: string }) =>
  apiRequest<Incident>("/api/incidents", { method: "POST", body: payload });
export const updateIncident = (id: string, payload: Partial<{ status: string; resolution: string }>) =>
  apiRequest<Incident>(`/api/incidents/${id}`, { method: "PATCH", body: payload });
