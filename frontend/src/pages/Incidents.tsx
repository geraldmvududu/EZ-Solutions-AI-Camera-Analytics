import { useEffect, useState, type FormEvent } from "react";
import { Layout } from "../components/layout/Layout";
import { SeverityBadge, StatusBadge } from "../components/ui/Badge";
import * as incidentsApi from "../api/misc";
import { getEvidenceClipUrl, getRecording } from "../api/misc";
import type { Incident, IncidentAlert } from "../api/misc";
import * as camerasApi from "../api/cameras";
import { getEvent } from "../api/events";
import type { Camera } from "../types";
import { VideoPlayerModal } from "./Recordings";

const REVIEW_DECISIONS = ["", "CONFIRMED", "FALSE_POSITIVE", "REQUIRES_INVESTIGATION", "DISMISSED", "ESCALATED"];

function IncidentDetailModal({
  incident,
  cameraName,
  onClose,
  onSaved,
}: {
  incident: Incident;
  cameraName: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [status, setStatus] = useState(incident.status);
  const [resolution, setResolution] = useState(incident.resolution);
  const [reviewDecision, setReviewDecision] = useState(incident.review_decision);
  const [saving, setSaving] = useState(false);
  const [viewingEvidenceClip, setViewingEvidenceClip] = useState(false);
  const [playback, setPlayback] = useState<{ recordingId: string; seekSeconds: number } | null>(null);

  async function handleViewRecording(alert: IncidentAlert) {
    if (!alert.recording_id) return;
    try {
      // Seek to the actual moment the violation occurred (the underlying Event's
      // occurred_at), not the Alert's own created_at — the alert row is inserted a
      // moment after the event in real-time operation, but they are not the same
      // field, and only occurred_at is the real timestamp to seek the video to.
      const [recording, event] = await Promise.all([getRecording(alert.recording_id), getEvent(alert.event_id)]);
      const seekSeconds = (new Date(event.occurred_at).getTime() - new Date(recording.started_at).getTime()) / 1000;
      setPlayback({ recordingId: alert.recording_id, seekSeconds: Math.max(0, seekSeconds) });
    } catch {
      /* recording may have been deleted by retention — no linked evidence to show */
    }
  }

  async function handleSave() {
    setSaving(true);
    try {
      await incidentsApi.updateIncident(incident.id, { status, resolution, review_decision: reviewDecision });
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
          <h3 className="font-semibold text-slate-100">{incident.title}</h3>
          <SeverityBadge severity={incident.severity} />
        </div>

        <div className="text-xs text-slate-500 space-y-1">
          <div>Camera: {cameraName}</div>
          <div>Opened: {new Date(incident.created_at).toLocaleString()}</div>
          {incident.closed_at && <div>Closed: {new Date(incident.closed_at).toLocaleString()}</div>}
        </div>

        {incident.incident_type && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="px-2 py-0.5 rounded bg-base-800 border border-base-700 text-slate-300">{incident.incident_type.replace(/_/g, " ")}</span>
            {incident.risk_score !== null && (
              <span className="px-2 py-0.5 rounded bg-base-800 border border-base-700 text-slate-300">Risk score: {incident.risk_score}/100</span>
            )}
            {incident.confidence !== null && (
              <span className="px-2 py-0.5 rounded bg-base-800 border border-base-700 text-slate-300">Confidence: {(incident.confidence * 100).toFixed(0)}%</span>
            )}
            {incident.requires_human_review && (
              <span className="px-2 py-0.5 rounded bg-amber-500/20 border border-amber-600 text-amber-300">Requires human review</span>
            )}
          </div>
        )}

        <div>
          <div className="text-xs text-slate-400 mb-1">Description</div>
          <p className="text-sm text-slate-200 bg-base-800 rounded border border-base-700 p-3 whitespace-pre-wrap">{incident.description || "—"}</p>
        </div>

        {incident.evidence_clip_path && (
          <div>
            <button onClick={() => setViewingEvidenceClip(true)} className="text-accent-500 hover:underline text-xs">
              View evidence clip (auto-generated, pre/post-event footage)
            </button>
          </div>
        )}

        {incident.related_alerts.length > 0 && (
          <div>
            <div className="text-xs text-slate-400 mb-1">Linked alerts / evidence</div>
            <div className="divide-y divide-base-700 rounded border border-base-700 overflow-hidden">
              {incident.related_alerts.map((a) => (
                <div key={a.id} className="px-3 py-2 text-xs flex items-center justify-between bg-base-800">
                  <div>
                    <div className="text-slate-200">{a.alert_type.replace(/_/g, " ")}</div>
                    <div className="text-slate-500">{new Date(a.created_at).toLocaleString()}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <SeverityBadge severity={a.severity} />
                    {a.snapshot_id && <span className="text-slate-500">Snapshot available</span>}
                    {a.recording_id && (
                      <button onClick={() => handleViewRecording(a)} className="text-accent-500 hover:underline">
                        View in recording
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <label className="block text-xs text-slate-400 mb-1">Status</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
            {["OPEN", "INVESTIGATING", "CONTAINED", "RESOLVED", "CLOSED"].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Resolution notes</label>
          <textarea value={resolution} onChange={(e) => setResolution(e.target.value)} rows={3} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Review decision</label>
          <select
            value={reviewDecision}
            onChange={(e) => setReviewDecision(e.target.value)}
            className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100"
          >
            {REVIEW_DECISIONS.map((d) => (
              <option key={d} value={d}>
                {d ? d.replace(/_/g, " ") : "— Not reviewed —"}
              </option>
            ))}
          </select>
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

      {viewingEvidenceClip && (
        <VideoPlayerModal
          recordingId={incident.id}
          src={getEvidenceClipUrl(incident.id)}
          title="Evidence clip"
          onClose={() => setViewingEvidenceClip(false)}
        />
      )}
    </div>
  );
}

export function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [viewing, setViewing] = useState<Incident | null>(null);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState("MEDIUM");

  function load() {
    incidentsApi.listIncidents().then(setIncidents).catch(() => {});
  }

  useEffect(() => {
    load();
    camerasApi.listCameras().then(setCameras).catch(() => {});
  }, []);

  function cameraName(cameraId: string | null): string {
    if (!cameraId) return "—";
    return cameras.find((c) => c.id === cameraId)?.name || "Unknown camera";
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    await incidentsApi.createIncident({ title, description, severity });
    setShowForm(false);
    setTitle("");
    setDescription("");
    load();
  }

  async function handleStatusChange(id: string, status: string) {
    await incidentsApi.updateIncident(id, { status });
    load();
  }

  return (
    <Layout title="Incidents">
      <div className="flex justify-between items-center mb-4">
        <div className="text-sm text-slate-400">{incidents.length} incident(s)</div>
        <button onClick={() => setShowForm(true)} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white">
          + New Incident
        </button>
      </div>

      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Title</th>
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-left px-4 py-2">Camera</th>
              <th className="text-left px-4 py-2">Severity</th>
              <th className="text-left px-4 py-2">Risk</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Created</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {incidents.map((i) => (
              <tr key={i.id}>
                <td className="px-4 py-2 text-slate-100">{i.title}</td>
                <td className="px-4 py-2 text-slate-400">{i.incident_type ? i.incident_type.replace(/_/g, " ") : "—"}</td>
                <td className="px-4 py-2 text-slate-400">{cameraName(i.camera_id)}</td>
                <td className="px-4 py-2">
                  <SeverityBadge severity={i.severity} />
                </td>
                <td className="px-4 py-2 text-slate-400">{i.risk_score !== null ? `${i.risk_score}/100` : "—"}</td>
                <td className="px-4 py-2">
                  <select
                    value={i.status}
                    onChange={(e) => handleStatusChange(i.id, e.target.value)}
                    className="rounded bg-base-800 border border-base-600 px-2 py-1 text-xs text-slate-100"
                  >
                    {["OPEN", "INVESTIGATING", "CONTAINED", "RESOLVED", "CLOSED"].map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-2 text-slate-500">{new Date(i.created_at).toLocaleString()}</td>
                <td className="px-4 py-2">
                  <button onClick={() => setViewing(i)} className="text-accent-500 hover:underline text-xs">
                    Open
                  </button>
                </td>
              </tr>
            ))}
            {incidents.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                  No incidents yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <form onSubmit={handleCreate} className="bg-base-900 border border-base-700 rounded-lg w-full max-w-md p-5 space-y-3">
            <h3 className="font-semibold text-slate-100 mb-2">New Incident</h3>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Title</label>
              <input required value={title} onChange={(e) => setTitle(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Description</label>
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" rows={3} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Severity</label>
              <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
                {["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowForm(false)} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
                Cancel
              </button>
              <button type="submit" className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white">
                Create
              </button>
            </div>
          </form>
        </div>
      )}

      {viewing && (
        <IncidentDetailModal incident={viewing} cameraName={cameraName(viewing.camera_id)} onClose={() => setViewing(null)} onSaved={load} />
      )}
    </Layout>
  );
}
