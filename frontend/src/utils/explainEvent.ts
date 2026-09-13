import type { EventItem } from "../types";

// Plain, deterministic explanations built only from the real event_type + the exact
// event_metadata fields ai-engine/backend are known to populate for that type (see
// worker.py/faces.py/violation_service.py) — never a guess at intent, never a claim
// this app can't back with evidence. Mirrors the tone of the backend's own
// auto-generated incident descriptions (violation_service.py): "detected"/"observed"/
// "potential", not "proven".

function pct(value: unknown): string | null {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : null;
}

function identityClause(metadata: Record<string, unknown>): string {
  const name = metadata.person_name;
  if (typeof name === "string" && name) {
    const confidence = pct(metadata.person_recognition_confidence ?? metadata.confidence);
    return `Identified via facial recognition as ${name}${confidence ? ` (confidence ${confidence})` : ""}.`;
  }
  return "";
}

export function explainEvent(event: EventItem): string {
  const m = event.event_metadata || {};

  switch (event.event_type) {
    case "GATE_JUMPING_DETECTED": {
      const confidence = pct(m.confidence);
      return [
        `A person was observed crossing a gate/fence boundary with a trajectory consistent with climbing or jumping rather than a normal walk-through${confidence ? ` (heuristic confidence ${confidence})` : ""}.`,
        identityClause(m),
        "This is a real-time trajectory heuristic, not a trained climbing/jumping classifier — review the linked evidence before treating this as confirmed.",
      ].filter(Boolean).join(" ");
    }
    case "TAILGATING_DETECTED": {
      const window = m.window_seconds;
      return [
        `A person crossed a controlled access point ${typeof window === "number" ? `within ${window}s of` : "shortly after"} another person's crossing, without a separate authorized entry in between.`,
        identityClause(m),
        "This platform has no access-control-system integration, so this is video-only evidence.",
      ].filter(Boolean).join(" ");
    }
    case "RESTRICTED_AREA_VIOLATION": {
      const threshold = m.threshold_seconds;
      return [
        `A person remained in a restricted area${typeof threshold === "number" ? ` for at least ${threshold} seconds` : ""}.`,
        identityClause(m),
        "Review the linked evidence before treating this as a confirmed violation.",
      ].filter(Boolean).join(" ");
    }
    case "LOITERING_DETECTED": {
      const threshold = m.threshold_seconds;
      return `A person remained in a monitored zone${typeof threshold === "number" ? ` for at least ${threshold} seconds` : ""} without leaving, exceeding the configured loitering threshold.`;
    }
    case "INTRUSION_DETECTED":
      return [`A person entered a restricted intrusion zone.`, identityClause(m)].filter(Boolean).join(" ");
    case "TRIPWIRE_VIOLATION": {
      const direction = m.direction;
      return [
        `A person crossed a monitored tripwire${typeof direction === "string" ? ` (direction: ${direction.toLowerCase()})` : ""}.`,
        identityClause(m),
      ].filter(Boolean).join(" ");
    }
    case "FACE_RECOGNIZED": {
      const name = m.person_name;
      const confidence = pct(m.confidence);
      return `A face was matched against an enrolled profile${typeof name === "string" && name ? `: ${name}` : ""}${confidence ? ` (confidence ${confidence})` : ""}. Facial recognition is an automated candidate match — verify identity through appropriate means before acting on it.`;
    }
    case "UNKNOWN_FACE_DETECTED":
      return "A face was detected but did not match any enrolled profile above the configured confidence threshold.";
    case "PERSON_DETECTED":
      return "A person was detected by the AI object detector.";
    case "VEHICLE_DETECTED": {
      const objType = m.object_type;
      return `A vehicle${typeof objType === "string" ? ` (${objType.toLowerCase()})` : ""} was detected by the AI object detector.`;
    }
    case "AI_DETECTION": {
      const objType = m.object_type;
      const confidence = pct(m.confidence);
      return `An object${typeof objType === "string" ? ` of type ${objType}` : ""} was detected${confidence ? ` (confidence ${confidence})` : ""}.`;
    }
    case "MOTION_DETECTED":
      return "Motion was detected in the camera's field of view (real background-subtraction motion detection).";
    case "CAMERA_ONLINE":
      return "The camera came back online.";
    case "CAMERA_OFFLINE":
      return "The camera went offline or stopped reporting a heartbeat.";
    case "RECORDING_FAILURE":
      return "The camera's recording pipeline reported a failure.";
    default:
      return event.description || "No further detail is available for this event type.";
  }
}
