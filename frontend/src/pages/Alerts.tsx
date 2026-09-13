import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { SeverityBadge, StatusBadge } from "../components/ui/Badge";
import { SnapshotImage } from "../components/ui/SnapshotImage";
import { listAlerts, updateAlert, getEvent } from "../api/events";
import * as camerasApi from "../api/cameras";
import { getRecording, listRules, type AIRule } from "../api/misc";
import { explainEvent } from "../utils/explainEvent";
import { useLiveFeed } from "../hooks/useLiveFeed";
import type { AlertItem, Camera, EventItem } from "../types";
import { useAuth } from "../context/AuthContext";
import { VideoPlayerModal } from "./Recordings";

function AlertDetailModal({
  alert,
  cameraName,
  ruleName,
  onClose,
  onSaved,
}: {
  alert: AlertItem;
  cameraName: string;
  ruleName: string | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [event, setEvent] = useState<EventItem | null>(null);
  const [eventError, setEventError] = useState<string | null>(null);
  const [status, setStatus] = useState(alert.status);
  const [notes, setNotes] = useState(alert.notes);
  const [saving, setSaving] = useState(false);
  const [playback, setPlayback] = useState<{ recordingId: string; seekSeconds: number } | null>(null);
  const [recordingError, setRecordingError] = useState<string | null>(null);

  useEffect(() => {
    getEvent(alert.event_id)
      .then(setEvent)
      .catch(() => setEventError("The underlying event could not be loaded."));
  }, [alert.event_id]);

  async function handleViewRecording() {
    if (!alert.recording_id) return;
    setRecordingError(null);
    try {
      // Seek to the actual moment the event occurred, not the alert's own created_at
      // (a DB-insert timestamp) — see Incidents.tsx for the same distinction.
      const occurredAt = event?.occurred_at ?? alert.created_at;
      const recording = await getRecording(alert.recording_id);
      const seekSeconds = (new Date(occurredAt).getTime() - new Date(recording.started_at).getTime()) / 1000;
      setPlayback({ recordingId: alert.recording_id, seekSeconds: Math.max(0, seekSeconds) });
    } catch {
      setRecordingError("The linked recording is no longer available (may have expired via retention).");
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      await updateAlert(alert.id, { status, notes });
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-base-900 border border-base-700 rounded-lg w-full max-w-lg p-5 space-y-4 max-h-[85vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-semibold text-slate-100">{alert.alert_type.replace(/_/g, " ")}</h3>
          <SeverityBadge severity={alert.severity} />
        </div>

        <div className="text-xs text-slate-500 space-y-1">
          <div>Camera: {cameraName}</div>
          <div>Triggered: {new Date(alert.created_at).toLocaleString()}</div>
          {ruleName && <div>Matched rule: {ruleName}</div>}
          {alert.acknowledged_at && <div>Acknowledged: {new Date(alert.acknowledged_at).toLocaleString()}</div>}
          {alert.resolved_at && <div>Resolved: {new Date(alert.resolved_at).toLocaleString()}</div>}
        </div>

        <div>
          <div className="text-xs text-slate-400 mb-1">Why this alert fired</div>
          {eventError && <div className="text-severity-critical text-xs">{eventError}</div>}
          {!eventError && (
            <p className="text-sm text-slate-200 bg-base-800 rounded border border-base-700 p-3 whitespace-pre-wrap">
              {event ? explainEvent(event) : "Loading…"}
            </p>
          )}
        </div>

        {(alert.snapshot_id || alert.recording_id) && (
          <div>
            <div className="text-xs text-slate-400 mb-1">Evidence</div>
            {alert.snapshot_id && <SnapshotImage snapshotId={alert.snapshot_id} className="w-full rounded border border-base-700 mb-2" />}
            {alert.recording_id && (
              <button onClick={handleViewRecording} className="text-accent-500 hover:underline text-xs">
                View in recording
              </button>
            )}
            {recordingError && <div className="text-severity-critical text-xs mt-1">{recordingError}</div>}
          </div>
        )}

        <div>
          <label className="block text-xs text-slate-400 mb-1">Status</label>
          <select value={status} onChange={(e) => setStatus(e.target.value as AlertItem["status"])} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
            {["NEW", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "FALSE_POSITIVE"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Notes</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
            Close
          </button>
          <button type="button" onClick={handleSave} disabled={saving} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50">
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>

      {playback && (
        <VideoPlayerModal recordingId={playback.recordingId} seekSeconds={playback.seekSeconds} onClose={() => setPlayback(null)} />
      )}
    </div>
  );
}

export function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [rules, setRules] = useState<AIRule[]>([]);
  const [viewing, setViewing] = useState<AlertItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { hasPermission } = useAuth();

  function load() {
    listAlerts({ limit: "200" })
      .then(setAlerts)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load alerts"));
  }

  useEffect(() => {
    load();
    camerasApi.listCameras().then(setCameras).catch(() => {});
    listRules().then(setRules).catch(() => {});
  }, []);

  useLiveFeed((message) => {
    if (message.type === "alert") setAlerts((prev) => [message.alert, ...prev]);
  }, true);

  async function handleStatusChange(id: string, status: string) {
    await updateAlert(id, { status });
    load();
  }

  function cameraName(cameraId: string): string {
    return cameras.find((c) => c.id === cameraId)?.name || "Unknown camera";
  }

  function ruleName(ruleId: string | null): string | null {
    if (!ruleId) return null;
    return rules.find((r) => r.id === ruleId)?.name || null;
  }

  const canManage = hasPermission("manage_alerts");

  return (
    <Layout title="Alerts">
      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}
      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-left px-4 py-2">Severity</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Created</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {alerts.map((a) => (
              <tr key={a.id}>
                <td className="px-4 py-2 text-slate-100">{a.alert_type.replace(/_/g, " ")}</td>
                <td className="px-4 py-2">
                  <SeverityBadge severity={a.severity} />
                </td>
                <td className="px-4 py-2">
                  <StatusBadge status={a.status} />
                </td>
                <td className="px-4 py-2 text-slate-500">{new Date(a.created_at).toLocaleString()}</td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-3">
                    <button onClick={() => setViewing(a)} className="text-accent-500 hover:underline text-xs">
                      View
                    </button>
                    {canManage && (
                      <select
                        value={a.status}
                        onChange={(e) => handleStatusChange(a.id, e.target.value)}
                        className="rounded bg-base-800 border border-base-600 px-2 py-1 text-xs text-slate-100"
                      >
                        {["NEW", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "FALSE_POSITIVE"].map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {alerts.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  No alerts yet. Alerts are generated automatically when a security rule matches a real event.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {viewing && (
        <AlertDetailModal
          alert={viewing}
          cameraName={cameraName(viewing.camera_id)}
          ruleName={ruleName(viewing.rule_id)}
          onClose={() => setViewing(null)}
          onSaved={load}
        />
      )}
    </Layout>
  );
}
