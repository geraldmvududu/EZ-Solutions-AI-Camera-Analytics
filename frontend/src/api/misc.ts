import { API_URL, apiRequest, tokenStore } from "./client";

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
export const getRecording = (id: string) => apiRequest<Recording>(`/api/recordings/${id}`);

// Same query-param-token pattern as cameras.ts::getStreamUrl — a <video src="..."> tag
// can't set an Authorization header.
export function getRecordingPlayUrl(recordingId: string): string {
  const token = tokenStore.getAccess() || "";
  return `${API_URL}/api/recordings/${recordingId}/play?token=${encodeURIComponent(token)}`;
}

// GET /snapshots/{id}/image needs a normal Authorization header (no query-token
// variant exists for it), so — same reasoning as faces.ts::fetchPersonPhoto — fetch it
// as a blob and hand back an object URL an <img> tag can use.
export async function fetchSnapshotImage(id: string): Promise<string | null> {
  const token = tokenStore.getAccess();
  const resp = await fetch(`${API_URL}/api/snapshots/${id}/image`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) return null;
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}

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

export interface IncidentAlert {
  id: string;
  event_id: string;
  camera_id: string;
  alert_type: string;
  severity: string;
  status: string;
  snapshot_id: string | null;
  recording_id: string | null;
  created_at: string;
}

export interface Incident {
  id: string;
  title: string;
  description: string;
  severity: string;
  camera_id: string | null;
  status: string;
  resolution: string;
  closed_at: string | null;
  created_at: string;
  related_alerts: IncidentAlert[];
  incident_type: string;
  confidence: number | null;
  risk_score: number | null;
  requires_human_review: boolean;
  review_decision: string;
  evidence_clip_path: string | null;
  source_event_id: string | null;
}

export const listIncidents = () => apiRequest<Incident[]>("/api/incidents");
export const createIncident = (payload: { title: string; description?: string; severity: string }) =>
  apiRequest<Incident>("/api/incidents", { method: "POST", body: payload });
export const updateIncident = (id: string, payload: Partial<{ status: string; resolution: string; review_decision: string }>) =>
  apiRequest<Incident>(`/api/incidents/${id}`, { method: "PATCH", body: payload });

export interface IncidentSummary {
  range_start: string;
  range_end: string;
  by_severity: { label: string; count: number }[];
  by_type: { label: string; count: number }[];
}

export const getIncidentSummary = (params: { start?: string; end?: string } = {}) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return apiRequest<IncidentSummary>(`/api/incidents/summary${qs ? `?${qs}` : ""}`);
};

export interface VideoIntelligenceSettings {
  id: string;
  tenant_id: string;
  gate_jumping_enabled: boolean;
  tailgating_enabled: boolean;
  restricted_area_enabled: boolean;
  min_confidence: number;
  pre_event_seconds: number;
  post_event_seconds: number;
  business_hours_start: string;
  business_hours_end: string;
}

export const getVideoIntelligenceSettings = () => apiRequest<VideoIntelligenceSettings>("/api/video-intelligence-settings");
export const updateVideoIntelligenceSettings = (payload: Partial<VideoIntelligenceSettings>) =>
  apiRequest<VideoIntelligenceSettings>("/api/video-intelligence-settings", { method: "PUT", body: payload });

// Same query-param-token pattern as getRecordingPlayUrl — a <video src="..."> can't
// set an Authorization header. Scoped by incident ID (not a raw file path) so a user
// can only ever fetch a clip belonging to an incident they're actually allowed to see.
export function getEvidenceClipUrl(incidentId: string): string {
  const token = tokenStore.getAccess() || "";
  return `${API_URL}/api/incidents/${incidentId}/evidence-clip?token=${encodeURIComponent(token)}`;
}
