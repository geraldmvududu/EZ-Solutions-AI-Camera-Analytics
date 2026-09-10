import { API_URL, apiRequest, tokenStore } from "./client";

export interface NamedCount {
  label: string;
  count: number;
}

export interface HourlyCount {
  hour: number;
  count: number;
}

export interface AnalyticsSummary {
  range_start: string;
  range_end: string;
  total_events: number;
  total_alerts: number;
  total_detections: number;
  events_by_camera: NamedCount[];
  events_by_hour: HourlyCount[];
  alerts_by_severity: NamedCount[];
  detections_by_object_type: NamedCount[];
  most_active_cameras: NamedCount[];
  camera_status_summary: NamedCount[];
  storage_used_bytes: number;
  storage_total_bytes: number;
}

export const getAnalyticsSummary = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return apiRequest<AnalyticsSummary>(`/api/analytics/summary${qs ? `?${qs}` : ""}`);
};

async function downloadAuthenticated(path: string, filename: string): Promise<void> {
  const token = tokenStore.getAccess();
  const resp = await fetch(`${API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error(`Download failed: ${resp.status}`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const downloadEventsCsv = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return downloadAuthenticated(`/api/reports/events.csv${qs ? `?${qs}` : ""}`, "events.csv");
};

export const downloadAlertsCsv = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return downloadAuthenticated(`/api/reports/alerts.csv${qs ? `?${qs}` : ""}`, "alerts.csv");
};

export const downloadSecurityReportPdf = (params: Record<string, string> = {}) => {
  const qs = new URLSearchParams(params).toString();
  return downloadAuthenticated(`/api/reports/security-report.pdf${qs ? `?${qs}` : ""}`, "security-report.pdf");
};
