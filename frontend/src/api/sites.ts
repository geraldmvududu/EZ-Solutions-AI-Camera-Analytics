import { apiRequest } from "./client";
import type { Site } from "../types";

export interface SiteCreatePayload {
  name: string;
  address?: string;
  timezone?: string;
}

export interface SiteUpdatePayload {
  name?: string;
  address?: string;
  timezone?: string;
  is_active?: boolean;
}

export const listSites = () => apiRequest<Site[]>("/api/sites");
export const createSite = (payload: SiteCreatePayload) => apiRequest<Site>("/api/sites", { method: "POST", body: payload });
export const updateSite = (id: string, payload: SiteUpdatePayload) => apiRequest<Site>(`/api/sites/${id}`, { method: "PATCH", body: payload });
export const deleteSite = (id: string) => apiRequest<void>(`/api/sites/${id}`, { method: "DELETE" });
