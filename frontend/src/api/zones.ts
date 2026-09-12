import { apiRequest } from "./client";

export type ZoneType = "INTRUSION" | "PRIVACY" | "LOITERING" | "FACE_DETECTION" | "FACE_EXCLUSION";
export type TripwireDirection = "ENTERING" | "EXITING" | "BOTH";

export interface Zone {
  id: string;
  camera_id: string;
  name: string;
  zone_type: ZoneType;
  polygon: [number, number][];
  loitering_threshold_seconds: number;
  is_enabled: boolean;
}

export interface Tripwire {
  id: string;
  camera_id: string;
  name: string;
  line: [number, number][];
  direction: TripwireDirection;
  is_enabled: boolean;
}

export const listZones = (cameraId: string) => apiRequest<Zone[]>(`/api/zones?camera_id=${cameraId}`);
export const createZone = (payload: {
  camera_id: string;
  name: string;
  zone_type: ZoneType;
  polygon: [number, number][];
  loitering_threshold_seconds?: number;
}) => apiRequest<Zone>("/api/zones", { method: "POST", body: payload });
export const deleteZone = (id: string) => apiRequest<void>(`/api/zones/${id}`, { method: "DELETE" });

export const listTripwires = (cameraId: string) => apiRequest<Tripwire[]>(`/api/tripwires?camera_id=${cameraId}`);
export const createTripwire = (payload: { camera_id: string; name: string; line: [number, number][]; direction: TripwireDirection }) =>
  apiRequest<Tripwire>("/api/tripwires", { method: "POST", body: payload });
export const deleteTripwire = (id: string) => apiRequest<void>(`/api/tripwires/${id}`, { method: "DELETE" });
