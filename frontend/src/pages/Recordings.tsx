import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { getRecordingPlayUrl, listRecordings, type Recording } from "../api/misc";

export function VideoPlayerModal({ recordingId, seekSeconds, onClose }: { recordingId: string; seekSeconds?: number; onClose: () => void }) {
  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="max-w-4xl w-full" onClick={(e) => e.stopPropagation()}>
        <div className="flex justify-between items-center mb-2">
          <div className="text-slate-100 font-semibold">Recording playback</div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-100 text-sm">
            Close ✕
          </button>
        </div>
        <video
          key={recordingId}
          src={getRecordingPlayUrl(recordingId)}
          controls
          autoPlay
          className="w-full rounded-lg bg-black"
          onLoadedMetadata={(e) => {
            if (seekSeconds && seekSeconds > 0) e.currentTarget.currentTime = seekSeconds;
          }}
        />
      </div>
    </div>
  );
}

export function RecordingsPage() {
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [playing, setPlaying] = useState<string | null>(null);

  useEffect(() => {
    listRecordings().then(setRecordings).catch(() => {});
  }, []);

  return (
    <Layout title="Recordings">
      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Started</th>
              <th className="text-left px-4 py-2">Duration</th>
              <th className="text-left px-4 py-2">Trigger</th>
              <th className="text-left px-4 py-2">Protected</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {recordings.map((r) => (
              <tr key={r.id}>
                <td className="px-4 py-2 text-slate-100">{new Date(r.started_at).toLocaleString()}</td>
                <td className="px-4 py-2 text-slate-400">{r.ended_at ? `${r.duration_seconds.toFixed(0)}s` : "Recording..."}</td>
                <td className="px-4 py-2 text-slate-400">{r.trigger_type}</td>
                <td className="px-4 py-2 text-slate-400">{r.is_protected ? "Locked" : "—"}</td>
                <td className="px-4 py-2">
                  <button onClick={() => setPlaying(r.id)} className="text-accent-500 hover:underline text-xs">
                    Play
                  </button>
                </td>
              </tr>
            ))}
            {recordings.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  No recordings yet. Recordings are written by the ai-engine's recorder service (Phase 2) as cameras
                  are processed.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {playing && <VideoPlayerModal recordingId={playing} onClose={() => setPlaying(null)} />}
    </Layout>
  );
}
