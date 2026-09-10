import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { listRecordings, type Recording } from "../api/misc";

export function RecordingsPage() {
  const [recordings, setRecordings] = useState<Recording[]>([]);

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
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {recordings.map((r) => (
              <tr key={r.id}>
                <td className="px-4 py-2 text-slate-100">{new Date(r.started_at).toLocaleString()}</td>
                <td className="px-4 py-2 text-slate-400">{r.duration_seconds}s</td>
                <td className="px-4 py-2 text-slate-400">{r.trigger_type}</td>
                <td className="px-4 py-2 text-slate-400">{r.is_protected ? "Locked" : "—"}</td>
              </tr>
            ))}
            {recordings.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                  No recordings yet. Recordings are written by the ai-engine's recorder service (Phase 2) as cameras
                  are processed.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Layout>
  );
}
