import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { SeverityBadge } from "../components/ui/Badge";
import { SnapshotImage } from "../components/ui/SnapshotImage";
import { listEvents } from "../api/events";
import * as camerasApi from "../api/cameras";
import { getRecording } from "../api/misc";
import { explainEvent } from "../utils/explainEvent";
import type { Camera, EventItem } from "../types";
import { VideoPlayerModal } from "./Recordings";

function EventDetailModal({ event, cameraName, onClose }: { event: EventItem; cameraName: string; onClose: () => void }) {
  const [playback, setPlayback] = useState<{ recordingId: string; seekSeconds: number } | null>(null);
  const [recordingError, setRecordingError] = useState<string | null>(null);

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

  const metadataEntries = Object.entries(event.event_metadata || {}).filter(([, v]) => v !== null && v !== undefined);

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-base-900 border border-base-700 rounded-lg w-full max-w-lg p-5 space-y-4 max-h-[85vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-semibold text-slate-100">{event.event_type.replace(/_/g, " ")}</h3>
          <SeverityBadge severity={event.severity} />
        </div>

        <div className="text-xs text-slate-500 space-y-1">
          <div>Camera: {cameraName}</div>
          <div>Occurred: {new Date(event.occurred_at).toLocaleString()}</div>
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

        <div className="flex justify-end pt-2">
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

  useEffect(() => {
    listEvents({ limit: "200" })
      .then(setEvents)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load events"));
    camerasApi.listCameras().then(setCameras).catch(() => {});
  }, []);

  function cameraName(cameraId: string): string {
    return cameras.find((c) => c.id === cameraId)?.name || "Unknown camera";
  }

  return (
    <Layout title="Events">
      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}
      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-left px-4 py-2">Severity</th>
              <th className="text-left px-4 py-2">Description</th>
              <th className="text-left px-4 py-2">Occurred</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {events.map((e) => (
              <tr key={e.id}>
                <td className="px-4 py-2 text-slate-100">{e.event_type.replace(/_/g, " ")}</td>
                <td className="px-4 py-2">
                  <SeverityBadge severity={e.severity} />
                </td>
                <td className="px-4 py-2 text-slate-400">{e.description || "—"}</td>
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
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  No events recorded yet. Events appear here once the AI engine (Phase 3) is processing camera feeds.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {viewing && <EventDetailModal event={viewing} cameraName={cameraName(viewing.camera_id)} onClose={() => setViewing(null)} />}
    </Layout>
  );
}
