import { useEffect, useState } from "react";
import { Layout } from "../../components/layout/Layout";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import * as vehiclesApi from "../../api/vehicles";
import type { VehicleWatchlistEntry, VehicleWatchlistStatus } from "../../api/vehicles";

const STATUS_OPTIONS: VehicleWatchlistStatus[] = ["AUTHORIZED", "UNAUTHORIZED", "WATCHLIST", "BLACKLISTED"];

const STATUS_COLOR: Record<VehicleWatchlistStatus, string> = {
  AUTHORIZED: "text-accent-500",
  UNAUTHORIZED: "text-slate-400",
  WATCHLIST: "text-severity-high",
  BLACKLISTED: "text-severity-critical",
};

function AddEntryForm({ onAdded }: { onAdded: () => void }) {
  const [plateText, setPlateText] = useState("");
  const [status, setStatus] = useState<VehicleWatchlistStatus>("WATCHLIST");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAdd() {
    if (!plateText.trim()) {
      setError("Enter a plate number first.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await vehiclesApi.createWatchlistEntry({ plate_text: plateText, status, description });
      setPlateText("");
      setDescription("");
      setStatus("WATCHLIST");
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add entry");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="rounded-lg border border-base-700 bg-base-900 p-4 mb-4 flex flex-wrap items-end gap-3">
      <div>
        <label className="block text-xs text-slate-400 mb-1">Plate Number</label>
        <input
          value={plateText}
          onChange={(e) => setPlateText(e.target.value)}
          placeholder="e.g. CA 123-456"
          className="rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100"
        />
      </div>
      <div>
        <label className="block text-xs text-slate-400 mb-1">Status</label>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as VehicleWatchlistStatus)}
          className="rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <div className="flex-1 min-w-[200px]">
        <label className="block text-xs text-slate-400 mb-1">Description</label>
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="e.g. Reported stolen"
          className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100"
        />
      </div>
      <button onClick={handleAdd} disabled={saving} className="px-4 py-2 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50">
        {saving ? "Adding..." : "Add"}
      </button>
      {error && <div className="w-full text-severity-critical text-xs">{error}</div>}
    </div>
  );
}

export function VehicleWatchlistPage() {
  const [entries, setEntries] = useState<VehicleWatchlistEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<VehicleWatchlistEntry | null>(null);

  function load() {
    vehiclesApi.listWatchlist().then(setEntries).catch((err) => setError(err instanceof Error ? err.message : "Failed to load watchlist"));
  }

  useEffect(load, []);

  async function handleStatusChange(entry: VehicleWatchlistEntry, status: VehicleWatchlistStatus) {
    await vehiclesApi.updateWatchlistEntry(entry.id, { status });
    load();
  }

  async function handleToggleActive(entry: VehicleWatchlistEntry) {
    await vehiclesApi.updateWatchlistEntry(entry.id, { is_active: !entry.is_active });
    load();
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    await vehiclesApi.deleteWatchlistEntry(deleteTarget.id);
    setDeleteTarget(null);
    load();
  }

  return (
    <Layout title="Vehicle Watchlist">
      <p className="text-xs text-slate-500 mb-4">
        Plates entered here are matched against real license-plate reads (Cameras page → "Plate Recognition (ANPR)" +
        "Multi-class object detection"). A plate NOT listed here is simply unknown — a plain sighting log entry, no
        alert. WATCHLIST/BLACKLISTED matches auto-create a real Incident.
      </p>

      <AddEntryForm onAdded={load} />

      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Plate</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Description</th>
              <th className="text-left px-4 py-2">Active</th>
              <th className="text-left px-4 py-2">Added</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {entries.map((e) => (
              <tr key={e.id}>
                <td className="px-4 py-2 text-slate-100 font-mono">{e.plate_text}</td>
                <td className="px-4 py-2">
                  <select
                    value={e.status}
                    onChange={(ev) => handleStatusChange(e, ev.target.value as VehicleWatchlistStatus)}
                    className={`rounded bg-base-800 border border-base-600 px-2 py-1 text-xs ${STATUS_COLOR[e.status]}`}
                  >
                    {STATUS_OPTIONS.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-2 text-slate-400">{e.description || "—"}</td>
                <td className="px-4 py-2">
                  <button onClick={() => handleToggleActive(e)} className={`text-xs hover:underline ${e.is_active ? "text-accent-500" : "text-slate-500"}`}>
                    {e.is_active ? "Active" : "Inactive"}
                  </button>
                </td>
                <td className="px-4 py-2 text-slate-500 text-xs">{new Date(e.created_at).toLocaleDateString()}</td>
                <td className="px-4 py-2">
                  <button onClick={() => setDeleteTarget(e)} className="text-severity-critical hover:underline text-xs">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                  No watchlist entries yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {deleteTarget && (
        <ConfirmDialog
          title="Delete watchlist entry"
          message={`Remove plate ${deleteTarget.plate_text} from the watchlist?`}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </Layout>
  );
}
