import { apiRequest } from "./client";

export type VehicleWatchlistStatus = "AUTHORIZED" | "UNAUTHORIZED" | "WATCHLIST" | "BLACKLISTED";

export interface VehicleWatchlistEntry {
  id: string;
  tenant_id: string;
  plate_text: string;
  status: VehicleWatchlistStatus;
  description: string;
  notes: string;
  is_active: boolean;
  created_at: string;
}

export const listWatchlist = () => apiRequest<VehicleWatchlistEntry[]>("/api/vehicles/watchlist");
export const createWatchlistEntry = (payload: { plate_text: string; status: VehicleWatchlistStatus; description?: string; notes?: string }) =>
  apiRequest<VehicleWatchlistEntry>("/api/vehicles/watchlist", { method: "POST", body: payload });
export const updateWatchlistEntry = (
  id: string,
  payload: Partial<{ status: VehicleWatchlistStatus; description: string; notes: string; is_active: boolean }>,
) => apiRequest<VehicleWatchlistEntry>(`/api/vehicles/watchlist/${id}`, { method: "PATCH", body: payload });
export const deleteWatchlistEntry = (id: string) => apiRequest<void>(`/api/vehicles/watchlist/${id}`, { method: "DELETE" });

export interface LicensePlateEvent {
  id: string;
  tenant_id: string;
  event_id: string;
  camera_id: string;
  watchlist_id: string | null;
  plate_text: string;
  vehicle_type: string;
  confidence: number;
  tracking_id: number;
  occurred_at: string;
  snapshot_id: string | null;
  recording_id: string | null;
  created_at: string;
}

export const listPlateEvents = (params: { plate_text?: string; camera_id?: string } = {}) => {
  const qs = new URLSearchParams(params as Record<string, string>).toString();
  return apiRequest<LicensePlateEvent[]>(`/api/vehicles/plate-events${qs ? `?${qs}` : ""}`);
};
