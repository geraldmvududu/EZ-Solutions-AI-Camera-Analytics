import { API_URL, apiRequest, apiUpload, tokenStore } from "./client";
import type { EnrollmentResult, FaceRecognitionEventItem, FaceStatistics, PersonCategory, PersonItem } from "../types";

export interface EnrollPayload {
  first_name: string;
  last_name: string;
  category: PersonCategory;
  external_reference?: string;
  department?: string;
  notes?: string;
  photo: File;
}

export function enrollFace(payload: EnrollPayload): Promise<EnrollmentResult> {
  const form = new FormData();
  form.set("first_name", payload.first_name);
  form.set("last_name", payload.last_name);
  form.set("category", payload.category);
  form.set("external_reference", payload.external_reference || "");
  form.set("department", payload.department || "");
  form.set("notes", payload.notes || "");
  form.set("photo", payload.photo);
  return apiUpload<EnrollmentResult>("/api/faces/enroll", form);
}

export const listPersons = (params?: { q?: string; category?: string; status?: string }) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return apiRequest<PersonItem[]>(`/api/faces${qs ? `?${qs}` : ""}`);
};

export const getPerson = (id: string) => apiRequest<PersonItem>(`/api/faces/${id}`);

export const updatePerson = (id: string, payload: Partial<PersonItem>) =>
  apiRequest<PersonItem>(`/api/faces/${id}`, { method: "PUT", body: payload });

export const deletePerson = (id: string) => apiRequest<void>(`/api/faces/${id}`, { method: "DELETE" });

// The photo endpoint requires the same JWT auth as every other API route (unlike the
// live-stream endpoint, which accepts a ?token= query param specifically because
// <img>/WebView can't set headers for a long-lived stream) — for a single still image
// it's simpler to fetch it as an authenticated blob and hand the component an object
// URL, rather than adding a second query-param-auth path on the backend.
export async function fetchPersonPhoto(id: string): Promise<string | null> {
  const token = tokenStore.getAccess();
  const resp = await fetch(`${API_URL}/api/faces/${id}/photo`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) return null;
  const blob = await resp.blob();
  return URL.createObjectURL(blob);
}

export const listFaceEvents = (params?: {
  camera_id?: string;
  person_id?: string;
  recognition_status?: string;
  reviewed?: boolean;
}) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return apiRequest<FaceRecognitionEventItem[]>(`/api/face-events${qs ? `?${qs}` : ""}`);
};

export const reviewFaceEvent = (id: string, decision: string, notes: string = "") =>
  apiRequest<FaceRecognitionEventItem>(`/api/face-events/${id}/review`, { method: "POST", body: { decision, notes } });

export const getFaceStatistics = () => apiRequest<FaceStatistics>("/api/face-statistics");

export const listFaceAlerts = () => apiRequest<Record<string, unknown>[]>("/api/face-alerts");

export const listFaceViolations = () => apiRequest<Record<string, unknown>[]>("/api/face-violations");

// Authenticated CSV download — same reasoning as fetchPersonPhoto: the endpoint needs
// the normal Authorization header, so this fetches it as a blob and triggers a real
// browser download rather than linking to it directly.
export async function downloadFaceAppearancesCsv(personId: string, personName: string): Promise<void> {
  const token = tokenStore.getAccess();
  const resp = await fetch(`${API_URL}/api/reports/face-appearances.csv?person_id=${personId}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!resp.ok) throw new Error("Failed to export appearance history");
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${personName.replace(/\s+/g, "-").toLowerCase()}-appearances.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
