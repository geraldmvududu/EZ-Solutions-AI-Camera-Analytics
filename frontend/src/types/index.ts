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
  face_recognition_enabled: boolean;
  face_recognition_threshold: number | null;
  face_operating_hours_start: string;
  face_operating_hours_end: string;
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
  | "AI_DETECTION"
  | "FACE_RECOGNIZED"
  | "UNKNOWN_FACE_DETECTED"
  | "GATE_JUMPING_DETECTED"
  | "TAILGATING_DETECTED"
  | "RESTRICTED_AREA_VIOLATION";

export interface EventItem {
  id: string;
  tenant_id: string;
  camera_id: string;
  event_type: EventType;
  severity: EventSeverity;
  description: string;
  detection_id: string | null;
  zone_id: string | null;
  tripwire_id: string | null;
  snapshot_id: string | null;
  recording_id: string | null;
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
  rule_id: string | null;
  alert_type: string;
  severity: EventSeverity;
  status: AlertStatus;
  snapshot_id: string | null;
  recording_id: string | null;
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

// ---- Facial Recognition & Identity Analytics ----

export type PersonCategory = "EMPLOYEE" | "CONTRACTOR" | "VISITOR" | "AUTHORIZED_PERSON" | "WATCHLIST";
export type PersonStatus = "ACTIVE" | "SUSPENDED" | "DELETED";
export type RecognitionStatus = "RECOGNIZED" | "UNKNOWN" | "LOW_CONFIDENCE";

export interface FaceProfileItem {
  id: string;
  person_id: string;
  model_version: string;
  quality_score: number;
  enrollment_date: string;
  status: "ACTIVE" | "SUSPENDED" | "DELETED";
}

export interface PersonItem {
  id: string;
  tenant_id: string;
  external_reference: string;
  first_name: string;
  last_name: string;
  category: PersonCategory;
  department: string;
  notes: string;
  status: PersonStatus;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  face_profiles: FaceProfileItem[];
}

export interface EnrollmentResult {
  success: boolean;
  message: string;
  person: PersonItem | null;
  quality_score: number | null;
}

export interface FaceRecognitionEventItem {
  id: string;
  tenant_id: string;
  event_id: string;
  camera_id: string;
  person_id: string | null;
  confidence_score: number;
  recognition_status: RecognitionStatus;
  model_version: string;
  event_timestamp: string;
  snapshot_id: string | null;
  recording_id: string | null;
  reviewed: boolean;
  review_decision: string;
  review_notes: string;
  reviewed_by: string | null;
  review_timestamp: string | null;
  created_at: string;
}

export interface FaceStatistics {
  recognized_today: number;
  unknown_faces_today: number;
  active_alerts: number;
  high_severity_active: number;
  violations_today: number;
  after_hours_events_today: number;
  restricted_area_events_today: number;
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
