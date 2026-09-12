import { API_URL, apiRequest, tokenStore } from "./client";
import type { Camera } from "../types";

export function getStreamUrl(cameraId: string): string {
  const token = tokenStore.getAccess() || "";
  return `${API_URL}/api/cameras/${cameraId}/stream?token=${encodeURIComponent(token)}`;
}

export interface CameraCreatePayload {
  name: string;
  location?: string;
  description?: string;
  source_type: string;
  stream_url?: string;
  username?: string;
  password?: string;
  video_file_path?: string;
  loop_video?: boolean;
  ai_fps?: number;
  ai_enabled?: boolean;
  motion_detection_enabled?: boolean;
  recording_enabled?: boolean;
  confidence_threshold?: number;
  face_recognition_enabled?: boolean;
  face_recognition_threshold?: number;
  face_operating_hours_start?: string;
  face_operating_hours_end?: string;
}

export const listCameras = () => apiRequest<Camera[]>("/api/cameras");
export const getCamera = (id: string) => apiRequest<Camera>(`/api/cameras/${id}`);
export const createCamera = (payload: CameraCreatePayload) =>
  apiRequest<Camera>("/api/cameras", { method: "POST", body: payload });
export const updateCamera = (id: string, payload: Partial<CameraCreatePayload & { is_active: boolean }>) =>
  apiRequest<Camera>(`/api/cameras/${id}`, { method: "PATCH", body: payload });
export const deleteCamera = (id: string) => apiRequest<void>(`/api/cameras/${id}`, { method: "DELETE" });
export const testCameraConnection = (id: string) =>
  apiRequest<{ success: boolean; detail: string }>(`/api/cameras/${id}/test-connection`, { method: "POST" });
