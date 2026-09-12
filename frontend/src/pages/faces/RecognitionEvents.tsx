import { useEffect, useState } from "react";
import { Layout } from "../../components/layout/Layout";
import * as facesApi from "../../api/faces";
import { getRecording } from "../../api/misc";
import { VideoPlayerModal } from "../Recordings";
import type { FaceRecognitionEventItem, RecognitionStatus } from "../../types";

const STATUS_LABEL: Record<RecognitionStatus, string> = {
  RECOGNIZED: "Recognized",
  UNKNOWN: "Unknown Person Detected",
  LOW_CONFIDENCE: "Low Confidence Match",
};

const STATUS_COLOR: Record<RecognitionStatus, string> = {
  RECOGNIZED: "text-accent-500",
  UNKNOWN: "text-severity-high",
  LOW_CONFIDENCE: "text-severity-medium",
};

function ReviewModal({ event, onClose, onReviewed }: { event: FaceRecognitionEventItem; onClose: () => void; onReviewed: () => void }) {
  const [decision, setDecision] = useState("CONFIRMED");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit() {
    setSubmitting(true);
    try {
      await facesApi.reviewFaceEvent(event.id, decision, notes);
      onReviewed();
      onClose();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-base-900 border border-base-700 rounded-lg w-full max-w-md p-5 space-y-3">
        <h3 className="font-semibold text-slate-100 mb-2">Review Event</h3>
        <div className="text-xs text-slate-500 space-y-1">
          <div>Camera: {event.camera_id}</div>
          <div>Time: {new Date(event.event_timestamp).toLocaleString()}</div>
          <div>Confidence: {(event.confidence_score * 100).toFixed(1)}%</div>
          <div>Status: {STATUS_LABEL[event.recognition_status]}</div>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Decision</label>
          <select value={decision} onChange={(e) => setDecision(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
            <option value="CONFIRMED">Confirm</option>
            <option value="REJECTED">Reject</option>
            <option value="FALSE_POSITIVE">False Positive</option>
            <option value="ESCALATED">Escalate</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Investigation notes</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onClose} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
            Cancel
          </button>
          <button onClick={handleSubmit} disabled={submitting} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50">
            {submitting ? "Saving..." : "Save Review"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function RecognitionEventsPage() {
  const [events, setEvents] = useState<FaceRecognitionEventItem[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [reviewing, setReviewing] = useState<FaceRecognitionEventItem | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playback, setPlayback] = useState<{ recordingId: string; seekSeconds: number } | null>(null);

  async function handleViewRecording(e: FaceRecognitionEventItem) {
    if (!e.recording_id) return;
    try {
      const recording = await getRecording(e.recording_id);
      const seekSeconds = (new Date(e.event_timestamp).getTime() - new Date(recording.started_at).getTime()) / 1000;
      setPlayback({ recordingId: e.recording_id, seekSeconds: Math.max(0, seekSeconds) });
    } catch {
      setError("Could not load the linked recording");
    }
  }

  async function load() {
    try {
      setEvents(await facesApi.listFaceEvents(statusFilter ? { recognition_status: statusFilter } : undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load recognition events");
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  return (
    <Layout title="Recognition Events">
      <div className="flex justify-between items-center mb-4">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
          <option value="">All statuses</option>
          <option value="RECOGNIZED">Recognized</option>
          <option value="UNKNOWN">Unknown</option>
          <option value="LOW_CONFIDENCE">Low Confidence</option>
        </select>
      </div>

      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Time</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Confidence</th>
              <th className="text-left px-4 py-2">Reviewed</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {events.map((e) => (
              <tr key={e.id}>
                <td className="px-4 py-2 text-slate-400 text-xs">{new Date(e.event_timestamp).toLocaleString()}</td>
                <td className={`px-4 py-2 font-medium ${STATUS_COLOR[e.recognition_status]}`}>{STATUS_LABEL[e.recognition_status]}</td>
                <td className="px-4 py-2 text-slate-400">{(e.confidence_score * 100).toFixed(1)}%</td>
                <td className="px-4 py-2 text-slate-400">{e.reviewed ? `Yes (${e.review_decision})` : "No"}</td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-3">
                    <button onClick={() => setReviewing(e)} className="text-accent-500 hover:underline text-xs">
                      Review
                    </button>
                    {e.recording_id && (
                      <button onClick={() => handleViewRecording(e)} className="text-accent-500 hover:underline text-xs">
                        View in recording
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  No recognition events yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {reviewing && <ReviewModal event={reviewing} onClose={() => setReviewing(null)} onReviewed={load} />}
      {playback && (
        <VideoPlayerModal recordingId={playback.recordingId} seekSeconds={playback.seekSeconds} onClose={() => setPlayback(null)} />
      )}
    </Layout>
  );
}
