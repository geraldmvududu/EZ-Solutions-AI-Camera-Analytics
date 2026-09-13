import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { SeverityBadge, StatusBadge } from "../components/ui/Badge";
import { SnapshotImage } from "../components/ui/SnapshotImage";
import { listEvents, reviewEvent, addEventNotes } from "../api/events";
import * as camerasApi from "../api/cameras";
import { getRecording } from "../api/misc";
import { downloadEventPdf } from "../api/analytics";
import { explainEvent } from "../utils/explainEvent";
import { useAuth } from "../context/AuthContext";
import type { Camera, EventCategory, EventItem, EventReviewStatus } from "../types";
import { VideoPlayerModal } from "./Recordings";

const EVENT_CATEGORIES: EventCategory[] = ["SECURITY", "PEOPLE", "VEHICLES", "SAFETY", "OPERATIONS"];
const SEVERITIES = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"];

function EventDetailModal({
  event,
  cameraName,
  onClose,
  onSaved,
}: {
  event: EventItem;
  cameraName: string;
  onClose: () => void;
  onSaved: (updated: EventItem) => void;
}) {
  const [playback, setPlayback] = useState<{ recordingId: string; seekSeconds: number } | null>(null);
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const [notes, setNotes] = useState(event.notes);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const { hasPermission } = useAuth();
  const canReview = hasPermission("manage_alerts");

  async function handleDownloadPdf() {
    setDownloadingPdf(true);
    try {
      await downloadEventPdf(event.id);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to download PDF");
    } finally {
      setDownloadingPdf(false);
    }
  }

  async function handleViewRecording() {
    if (!event.recording_id) return;
    setRecordingError(null);
    try {
      const recording = await getRecording(event.recording_id);
      const seekSeconds = (new Date(event.occurred_at).getTime() - new Date(recording.started_at).getTime()) / 1000;
      setPlayback({ recordingId: event.recording_id, seekSeconds: Math.max(0, seekSeconds) });
    } catch {
      setRecordingError("The linked recording is no longer available (may have expired via retention).");
    }
  }

  async function handleToggleReview() {
    setSaving(true);
    setSaveError(null);
    try {
      const nextStatus: EventReviewStatus = event.status === "REVIEWED" ? "UNREVIEWED" : "REVIEWED";
      const updated = await reviewEvent(event.id, nextStatus);
      onSaved(updated);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to update review status");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveNotes() {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await addEventNotes(event.id, notes);
      onSaved(updated);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save notes");
    } finally {
      setSaving(false);
    }
  }

  const metadataEntries = Object.entries(event.event_metadata || {}).filter(([, v]) => v !== null && v !== undefined);

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-base-900 border border-base-700 rounded-lg w-full max-w-lg p-5 space-y-4 max-h-[85vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-semibold text-slate-100">{event.event_type.replace(/_/g, " ")}</h3>
          <div className="flex items-center gap-2">
            <StatusBadge status={event.status} />
            <SeverityBadge severity={event.severity} />
          </div>
        </div>

        <div className="text-xs text-slate-500 space-y-1">
          <div>Camera: {cameraName}</div>
          <div>Category: {event.event_category}</div>
          <div>Occurred: {new Date(event.occurred_at).toLocaleString()}</div>
          {event.reviewed_at && <div>Reviewed: {new Date(event.reviewed_at).toLocaleString()}</div>}
        </div>

        <div>
          <div className="text-xs text-slate-400 mb-1">Explanation</div>
          <p className="text-sm text-slate-200 bg-base-800 rounded border border-base-700 p-3 whitespace-pre-wrap">{explainEvent(event)}</p>
        </div>

        {event.description && (
          <div>
            <div className="text-xs text-slate-400 mb-1">Description</div>
            <p className="text-sm text-slate-300">{event.description}</p>
          </div>
        )}

        {metadataEntries.length > 0 && (
          <div>
            <div className="text-xs text-slate-400 mb-1">Raw detection data</div>
            <div className="text-xs text-slate-400 bg-base-800 rounded border border-base-700 divide-y divide-base-700">
              {metadataEntries.map(([key, value]) => (
                <div key={key} className="flex justify-between px-3 py-1.5">
                  <span className="text-slate-500">{key.replace(/_/g, " ")}</span>
                  <span className="text-slate-200">{String(value)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {(event.snapshot_id || event.recording_id) && (
          <div>
            <div className="text-xs text-slate-400 mb-1">Evidence</div>
            {event.snapshot_id && <SnapshotImage snapshotId={event.snapshot_id} className="w-full rounded border border-base-700 mb-2" />}
            {event.recording_id && (
              <button onClick={handleViewRecording} className="text-accent-500 hover:underline text-xs">
                View in recording
              </button>
            )}
            {recordingError && <div className="text-severity-critical text-xs mt-1">{recordingError}</div>}
          </div>
        )}

        {canReview && (
          <div className="border-t border-base-700 pt-3 space-y-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Investigation notes</label>
              <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
            </div>
            {saveError && <div className="text-severity-critical text-xs">{saveError}</div>}
            <div className="flex justify-between gap-2">
              <button type="button" onClick={handleToggleReview} disabled={saving} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300 disabled:opacity-50">
                {event.status === "REVIEWED" ? "Mark as Unreviewed" : "Mark as Reviewed"}
              </button>
              <button type="button" onClick={handleSaveNotes} disabled={saving} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50">
                {saving ? "Saving..." : "Save Note"}
              </button>
            </div>
          </div>
        )}

        <div className="flex justify-between pt-2">
          <button type="button" onClick={handleDownloadPdf} disabled={downloadingPdf} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300 disabled:opacity-50">
            {downloadingPdf ? "Downloading..." : "Download PDF"}
          </button>
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
            Close
          </button>
        </div>
      </div>

      {playback && (
        <VideoPlayerModal recordingId={playback.recordingId} seekSeconds={playback.seekSeconds} onClose={() => setPlayback(null)} />
      )}
    </div>
  );
}

export function EventsPage() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [viewing, setViewing] = useState<EventItem | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [cameraFilter, setCameraFilter] = useState("");
  const [severityFilter, setSeverityFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [startFilter, setStartFilter] = useState("");
  const [endFilter, setEndFilter] = useState("");

  function load() {
    const params: Record<string, string> = { limit: "200" };
    if (cameraFilter) params.camera_id = cameraFilter;
    if (severityFilter) params.severity = severityFilter;
    if (categoryFilter) params.event_category = categoryFilter;
    if (statusFilter) params.status = statusFilter;
    if (startFilter) params.start = new Date(startFilter).toISOString();
    if (endFilter) params.end = new Date(endFilter).toISOString();

    listEvents(params)
      .then(setEvents)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load events"));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraFilter, severityFilter, categoryFilter, statusFilter, startFilter, endFilter]);

  useEffect(() => {
    camerasApi.listCameras().then(setCameras).catch(() => {});
  }, []);

  function cameraName(cameraId: string): string {
    return cameras.find((c) => c.id === cameraId)?.name || "Unknown camera";
  }

  function handleSaved(updated: EventItem) {
    setEvents((prev) => prev.map((e) => (e.id === updated.id ? updated : e)));
    setViewing(updated);
  }

  const selectClass = "rounded bg-base-800 border border-base-600 px-2 py-1.5 text-xs text-slate-100";

  return (
    <Layout title="Events">
      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      <div className="flex flex-wrap items-center gap-2 mb-4">
        <select value={cameraFilter} onChange={(e) => setCameraFilter(e.target.value)} className={selectClass}>
          <option value="">All cameras</option>
          {cameras.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value)} className={selectClass}>
          <option value="">All severities</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className={selectClass}>
          <option value="">All categories</option>
          {EVENT_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={selectClass}>
          <option value="">All review statuses</option>
          <option value="UNREVIEWED">Unreviewed</option>
          <option value="REVIEWED">Reviewed</option>
        </select>
        <input type="datetime-local" value={startFilter} onChange={(e) => setStartFilter(e.target.value)} className={selectClass} />
        <span className="text-slate-500 text-xs">to</span>
        <input type="datetime-local" value={endFilter} onChange={(e) => setEndFilter(e.target.value)} className={selectClass} />
      </div>

      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-left px-4 py-2">Category</th>
              <th className="text-left px-4 py-2">Severity</th>
              <th className="text-left px-4 py-2">Review</th>
              <th className="text-left px-4 py-2">Description</th>
              <th className="text-left px-4 py-2">Occurred</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {events.map((e) => (
              <tr key={e.id}>
                <td className="px-4 py-2 text-slate-100">{e.event_type.replace(/_/g, " ")}</td>
                <td className="px-4 py-2 text-slate-400">{e.event_category}</td>
                <td className="px-4 py-2">
                  <SeverityBadge severity={e.severity} />
                </td>
                <td className="px-4 py-2">
                  <StatusBadge status={e.status} />
                </td>
                <td className="px-4 py-2 text-slate-400 max-w-xs truncate" title={e.description || explainEvent(e)}>{e.description || explainEvent(e)}</td>
                <td className="px-4 py-2 text-slate-500">{new Date(e.occurred_at).toLocaleString()}</td>
                <td className="px-4 py-2">
                  <button onClick={() => setViewing(e)} className="text-accent-500 hover:underline text-xs">
                    View
                  </button>
                </td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                  No events match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {viewing && (
        <EventDetailModal event={viewing} cameraName={cameraName(viewing.camera_id)} onClose={() => setViewing(null)} onSaved={handleSaved} />
      )}
    </Layout>
  );
}
