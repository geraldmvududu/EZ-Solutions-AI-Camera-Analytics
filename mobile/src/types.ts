export interface CurrentUser {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: string;
  permissions: string[];
}

export interface Camera {
  id: string;
  camera_code: string;
  name: string;
  location: string;
  status: "ONLINE" | "OFFLINE" | "ERROR" | "DISABLED";
  ai_enabled: boolean;
  recording_enabled: boolean;
  capture_fps: number;
}

export interface AlertItem {
  id: string;
  alert_type: string;
  severity: "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  status: string;
  camera_id: string;
  created_at: string;
}
