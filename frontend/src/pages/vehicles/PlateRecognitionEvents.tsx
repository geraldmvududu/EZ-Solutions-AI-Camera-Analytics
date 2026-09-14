import { useEffect, useState } from "react";
import { Layout } from "../../components/layout/Layout";
import * as vehiclesApi from "../../api/vehicles";
import type { LicensePlateEvent } from "../../api/vehicles";
import { getRecording } from "../../api/misc";
import { VideoPlayerModal } from "../Recordings";

export function PlateRecognitionEventsPage() {
  const [events, setEvents] = useState<LicensePlateEvent[]>([]);
  const [plateFilter, setPlateFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [playback, setPlayback] = useState<{ recordingId: string; seekSeconds: number } | null>(null);

  function load() {
    vehiclesApi
      .listPlateEvents(plateFilter.trim() ? { plate_text: plateFilter.trim() } : {})
      .then(setEvents)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load plate recognition events"));
  }

  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleViewRecording(e: LicensePlateEvent) {
    if (!e.recording_id) return;
    try {
      const recording = await getRecording(e.recording_id);
      const seekSeconds = (new Date(e.occurred_at).getTime() - new Date(recording.started_at).getTime()) / 1000;
      setPlayback({ recordingId: e.recording_id, seekSeconds: Math.max(0, seekSeconds) });
    } catch {
      setError("Could not load the linked recording");
    }
  }

  return (
    <Layout title="Plate Recognition Events">
      <p className="text-xs text-slate-500 mb-4">
        Every real plate read (regardless of watchlist match) — supports "show all sightings of registration X".
        Manage watchlist status on the Vehicle Watchlist page.
      </p>

      <div className="flex items-end gap-3 mb-4">
        <div>
          <label className="block text-xs text-slate-400 mb-1">Search by plate</label>
          <input
            value={plateFilter}
            onChange={(e) => setPlateFilter(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && load()}
            placeholder="e.g. CA123456"
            className="rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100"
          />
        </div>
        <button onClick={load} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
          Search
        </button>
      </div>

      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Time</th>
              <th className="text-left px-4 py-2">Plate</th>
              <th className="text-left px-4 py-2">Vehicle Type</th>
              <th className="text-left px-4 py-2">OCR Confidence</th>
              <th className="text-left px-4 py-2">Watchlist</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {events.map((e) => (
              <tr key={e.id}>
                <td className="px-4 py-2 text-slate-400 text-xs">{new Date(e.occurred_at).toLocaleString()}</td>
                <td className="px-4 py-2 text-slate-100 font-mono">{e.plate_text}</td>
                <td className="px-4 py-2 text-slate-400">{e.vehicle_type}</td>
                <td className="px-4 py-2 text-slate-400">{(e.confidence * 100).toFixed(0)}%</td>
                <td className="px-4 py-2">
                  {e.watchlist_id ? (
                    <span className="text-severity-high">Match</span>
                  ) : (
                    <span className="text-slate-500">—</span>
                  )}
                </td>
                <td className="px-4 py-2">
                  {e.recording_id && (
                    <button onClick={() => handleViewRecording(e)} className="text-accent-500 hover:underline text-xs">
                      View in recording
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                  No plate recognition events yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {playback && (
        <VideoPlayerModal recordingId={playback.recordingId} seekSeconds={playback.seekSeconds} onClose={() => setPlayback(null)} />
      )}
    </Layout>
  );
}
