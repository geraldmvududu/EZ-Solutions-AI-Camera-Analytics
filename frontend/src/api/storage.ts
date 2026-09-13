import { apiRequest } from "./client";
import type { StorageUsage } from "../types";

export const getStorageUsage = () => apiRequest<StorageUsage>("/api/storage/usage");
