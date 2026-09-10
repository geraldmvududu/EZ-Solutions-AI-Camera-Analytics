export type Role = "SUPER_ADMIN" | "ADMIN" | "OPERATOR" | "VIEWER";

export interface CurrentUser {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: Role;
  permissions: string[];
}

export type CameraSourceType = "VIDEO_FILE" | "SIMULATED" | "WEBCAM" | "RTSP" | "HTTP_MJPEG" | "IP_CAMERA";
export type CameraStatus = "ONLINE" | "OFFLINE" | "ERROR" | "DISABLED";
export type RecordingMode = "CONTINUOUS" | "MOTION" | "AI_EVENT" | "DISABLED";

export interface Camera {
  id: string;
  tenant_id: string;
  camera_code: string;
  name: string;
  location: string;
  description: string;
  source_type: CameraSourceType;
  video_file_path: string;
  loop_video: boolean;
  resolution_width: number;
  resolution_height: number;
  capture_fps: number;
  ai_fps: number;
  ai_enabled: boolean;
  motion_detection_enabled: boolean;
  motion_sensitivity: string;
  recording_enabled: boolean;
  recording_mode: RecordingMode;
  retention_days: number;
  confidence_threshold: number;
  status: CameraStatus;
  is_active: boolean;
  is_demo: boolean;
  last_heartbeat_at: string | null;
  created_at: string;
}

export type EventSeverity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type EventType =
  | "PERSON_DETECTED"
  | "VEHICLE_DETECTED"
  | "MOTION_DETECTED"
  | "TRIPWIRE_VIOLATION"
  | "INTRUSION_DETECTED"
  | "LOITERING_DETECTED"
  | "CAMERA_OFFLINE"
  | "CAMERA_ONLINE"
  | "RECORDING_FAILURE"
  | "AI_DETECTION";

export interface EventItem {
  id: string;
  tenant_id: string;
  camera_id: string;
  event_type: EventType;
  severity: EventSeverity;
  description: string;
  occurred_at: string;
  event_metadata: Record<string, unknown>;
  is_demo: boolean;
  created_at: string;
}

export type AlertStatus = "NEW" | "ACKNOWLEDGED" | "INVESTIGATING" | "RESOLVED" | "FALSE_POSITIVE";

export interface AlertItem {
  id: string;
  tenant_id: string;
  event_id: string;
  camera_id: string;
  alert_type: string;
  severity: EventSeverity;
  status: AlertStatus;
  notes: string;
  assigned_user_id: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface DashboardStats {
  total_cameras: number;
  online_cameras: number;
  offline_cameras: number;
  active_alerts: number;
  critical_alerts: number;
  events_today: number;
  people_detected_today: number;
  vehicles_detected_today: number;
  motion_events_today: number;
  ai_events_today: number;
  recording_cameras: number;
  storage_used_bytes: number;
  storage_total_bytes: number;
  cpu_percent: number;
  ram_percent: number;
  ai_processing_device: string;
}

export interface ComponentHealth {
  component: string;
  status: string;
  message: string;
  metrics: Record<string, unknown>;
}

export interface SystemHealth {
  overall_status: string;
  components: ComponentHealth[];
  cpu_percent: number;
  ram_percent: number;
  disk_percent: number;
  ai_device: string;
}

export interface UserItem {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
}
