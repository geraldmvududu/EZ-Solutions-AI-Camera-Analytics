import { useEffect, useState } from "react";
import { Layout } from "../../components/layout/Layout";
import * as facesApi from "../../api/faces";
import { getRecording } from "../../api/misc";
import { VideoPlayerModal } from "../Recordings";
import type { FaceRecognitionEventItem, PersonItem, PersonStatus } from "../../types";

function PersonPhoto({ personId }: { personId: string }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    facesApi.fetchPersonPhoto(personId).then((u) => {
      if (cancelled) return;
      objectUrl = u;
      setUrl(u);
    });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [personId]);

  return url ? (
    <img src={url} alt="" className="h-10 w-10 rounded object-cover border border-base-600" />
  ) : (
    <div className="h-10 w-10 rounded bg-base-800 border border-base-600" />
  );
}

function AppearancesModal({ person, onClose }: { person: PersonItem; onClose: () => void }) {
  const [events, setEvents] = useState<FaceRecognitionEventItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [playback, setPlayback] = useState<{ recordingId: string; seekSeconds: number } | null>(null);

  useEffect(() => {
    facesApi.listFaceEvents({ person_id: person.id }).then(setEvents).catch(() => setError("Failed to load appearance history"));
  }, [person.id]);

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

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-base-900 border border-base-700 rounded-lg w-full max-w-2xl p-5 space-y-4 max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-slate-100">{person.first_name} {person.last_name} — Appearances</h3>
          <button
            onClick={() => facesApi.downloadFaceAppearancesCsv(person.id, `${person.first_name}-${person.last_name}`)}
            className="px-3 py-1.5 text-xs rounded border border-base-600 text-slate-300 hover:text-slate-100"
          >
            Export CSV
          </button>
        </div>

        {error && <div className="text-severity-critical text-sm">{error}</div>}

        <div className="rounded border border-base-700 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-base-800 text-slate-400 text-xs uppercase">
              <tr>
                <th className="text-left px-3 py-2">Time</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-left px-3 py-2">Confidence</th>
                <th className="text-left px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-base-700">
              {events.map((e) => (
                <tr key={e.id}>
                  <td className="px-3 py-2 text-slate-400 text-xs">{new Date(e.event_timestamp).toLocaleString()}</td>
                  <td className="px-3 py-2 text-slate-200">{e.recognition_status.replace(/_/g, " ")}</td>
                  <td className="px-3 py-2 text-slate-400">{(e.confidence_score * 100).toFixed(1)}%</td>
                  <td className="px-3 py-2">
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
                  <td colSpan={4} className="px-3 py-6 text-center text-slate-500">
                    No recognition events for this person yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex justify-end">
          <button onClick={onClose} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
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

export function EnrolledPeoplePage() {
  const [people, setPeople] = useState<PersonItem[]>([]);
  const [q, setQ] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [viewingAppearances, setViewingAppearances] = useState<PersonItem | null>(null);

  async function load(query?: string) {
    try {
      setPeople(await facesApi.listPersons(query ? { q: query } : undefined));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load enrolled people");
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleStatusChange(person: PersonItem, status: PersonStatus) {
    await facesApi.updatePerson(person.id, { status });
    load(q);
  }

  async function handleDelete(person: PersonItem) {
    if (!confirm(`Delete ${person.first_name} ${person.last_name}? This permanently removes their biometric data.`)) return;
    await facesApi.deletePerson(person.id);
    load(q);
  }

  return (
    <Layout title="Enrolled People">
      <div className="flex justify-between items-center mb-4 gap-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && load(q)}
          placeholder="Search by name or reference number..."
          className="w-full max-w-sm rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100"
        />
        <button onClick={() => load(q)} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300 shrink-0">
          Search
        </button>
      </div>

      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Photo</th>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">Reference</th>
              <th className="text-left px-4 py-2">Category</th>
              <th className="text-left px-4 py-2">Department</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Enrolled</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {people.map((p) => (
              <tr key={p.id}>
                <td className="px-4 py-2">
                  <PersonPhoto personId={p.id} />
                </td>
                <td className="px-4 py-2 text-slate-100">{p.first_name} {p.last_name}</td>
                <td className="px-4 py-2 text-slate-400">{p.external_reference || "—"}</td>
                <td className="px-4 py-2 text-slate-400">{p.category.replace(/_/g, " ")}</td>
                <td className="px-4 py-2 text-slate-400">{p.department || "—"}</td>
                <td className="px-4 py-2">
                  <select
                    value={p.status}
                    onChange={(e) => handleStatusChange(p, e.target.value as PersonStatus)}
                    disabled={p.status === "DELETED"}
                    className="rounded bg-base-800 border border-base-600 px-2 py-1 text-xs text-slate-100"
                  >
                    <option value="ACTIVE">Active</option>
                    <option value="SUSPENDED">Suspended</option>
                    {p.status === "DELETED" && <option value="DELETED">Deleted</option>}
                  </select>
                </td>
                <td className="px-4 py-2 text-slate-500 text-xs">
                  {p.face_profiles[0] ? new Date(p.face_profiles[0].enrollment_date).toLocaleDateString() : "—"}
                </td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-3">
                    <button onClick={() => setViewingAppearances(p)} className="text-accent-500 hover:underline text-xs">
                      Appearances
                    </button>
                    {p.status !== "DELETED" && (
                      <button onClick={() => handleDelete(p)} className="text-severity-critical hover:underline text-xs">
                        Delete
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {people.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                  No enrolled people yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {viewingAppearances && <AppearancesModal person={viewingAppearances} onClose={() => setViewingAppearances(null)} />}
    </Layout>
  );
}
