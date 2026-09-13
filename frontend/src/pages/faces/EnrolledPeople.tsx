import { useEffect, useRef, useState } from "react";
import { Layout } from "../../components/layout/Layout";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import * as facesApi from "../../api/faces";
import { getRecording } from "../../api/misc";
import { VideoPlayerModal } from "../Recordings";
import type { FaceRecognitionEventItem, PersonCategory, PersonItem, PersonStatus } from "../../types";

// Shared by both the table thumbnail and the edit modal's larger preview — refetches
// whenever `version` changes, so a just-uploaded replacement photo shows immediately
// without needing a full page reload (the backend URL itself never changes, only the
// underlying file/profile it serves).
function PersonPhoto({ personId, className, version }: { personId: string; className?: string; version?: number }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    setUrl(null);
    facesApi.fetchPersonPhoto(personId).then((u) => {
      if (cancelled) return;
      objectUrl = u;
      setUrl(u);
    });
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [personId, version]);

  return url ? (
    <img src={url} alt="" className={className ?? "h-10 w-10 rounded object-cover border border-base-600"} />
  ) : (
    <div className={className ?? "h-10 w-10 rounded bg-base-800 border border-base-600"} />
  );
}

const PERSON_CATEGORIES: PersonCategory[] = ["EMPLOYEE", "CONTRACTOR", "VISITOR", "AUTHORIZED_PERSON", "WATCHLIST"];

function EditPersonModal({ person, onClose, onSaved }: { person: PersonItem; onClose: () => void; onSaved: () => void }) {
  const [firstName, setFirstName] = useState(person.first_name);
  const [lastName, setLastName] = useState(person.last_name);
  const [category, setCategory] = useState<PersonCategory>(person.category);
  const [department, setDepartment] = useState(person.department);
  const [externalReference, setExternalReference] = useState(person.external_reference);
  const [notes, setNotes] = useState(person.notes);
  const [photoVersion, setPhotoVersion] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleReplacePhoto(file: File) {
    setUploading(true);
    setError(null);
    try {
      const result = await facesApi.updatePersonPhoto(person.id, file);
      if (!result.success) {
        setError(result.message);
        return;
      }
      setPhotoVersion((v) => v + 1);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update photo");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  async function handleSaveDetails() {
    setSaving(true);
    setError(null);
    try {
      await facesApi.updatePerson(person.id, {
        first_name: firstName,
        last_name: lastName,
        category,
        department,
        external_reference: externalReference,
        notes,
      });
      setSavedAt(Date.now());
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save changes");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-base-900 border border-base-700 rounded-lg w-full max-w-md p-5 space-y-4 max-h-[85vh] overflow-y-auto">
        <h3 className="font-semibold text-slate-100">Edit {person.first_name} {person.last_name}</h3>

        {error && <div className="text-severity-critical text-sm">{error}</div>}

        <div>
          <div className="text-xs text-slate-400 mb-2">Enrolled photo</div>
          <div className="flex items-center gap-4">
            <PersonPhoto
              personId={person.id}
              version={photoVersion}
              className="h-28 w-28 rounded object-cover border border-base-600"
            />
            <div className="space-y-2">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={(e) => e.target.files?.[0] && handleReplacePhoto(e.target.files[0])}
                disabled={uploading}
                className="text-xs text-slate-400"
              />
              <p className="text-xs text-slate-500 max-w-[220px]">
                {uploading ? "Uploading..." : "Replace with a new photo — subject to the same quality checks as enrollment."}
              </p>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">First name</label>
            <input value={firstName} onChange={(e) => setFirstName(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Last name</label>
            <input value={lastName} onChange={(e) => setLastName(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
          </div>
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Category</label>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as PersonCategory)}
            className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100"
          >
            {PERSON_CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Reference</label>
            <input value={externalReference} onChange={(e) => setExternalReference(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Department</label>
            <input value={department} onChange={(e) => setDepartment(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
          </div>
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Notes</label>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>

        <div className="flex items-center justify-end gap-3 pt-2">
          {savedAt && <span className="text-xs text-slate-500">Saved.</span>}
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
            Close
          </button>
          <button type="button" onClick={handleSaveDetails} disabled={saving} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50">
            {saving ? "Saving..." : "Save"}
          </button>
        </div>
      </div>
    </div>
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
  const [editingPerson, setEditingPerson] = useState<PersonItem | null>(null);
  const [photoVersions, setPhotoVersions] = useState<Record<string, number>>({});
  const [deleteTarget, setDeleteTarget] = useState<PersonItem | null>(null);

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

  async function confirmDelete() {
    if (!deleteTarget) return;
    await facesApi.deletePerson(deleteTarget.id);
    setDeleteTarget(null);
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
                  <PersonPhoto personId={p.id} version={photoVersions[p.id]} />
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
                    {p.status !== "DELETED" && (
                      <button onClick={() => setEditingPerson(p)} className="text-accent-500 hover:underline text-xs">
                        Edit
                      </button>
                    )}
                    <button onClick={() => setViewingAppearances(p)} className="text-accent-500 hover:underline text-xs">
                      Appearances
                    </button>
                    {p.status !== "DELETED" && (
                      <button onClick={() => setDeleteTarget(p)} className="text-severity-critical hover:underline text-xs">
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

      {editingPerson && (
        <EditPersonModal
          person={editingPerson}
          onClose={() => setEditingPerson(null)}
          onSaved={() => {
            setPhotoVersions((prev) => ({ ...prev, [editingPerson.id]: (prev[editingPerson.id] || 0) + 1 }));
            load(q);
          }}
        />
      )}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete enrolled person"
          message={`Delete ${deleteTarget.first_name} ${deleteTarget.last_name}? This permanently removes their biometric data.`}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </Layout>
  );
}
