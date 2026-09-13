import { useEffect, useState, type FormEvent } from "react";
import { Layout } from "../components/layout/Layout";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import * as sitesApi from "../api/sites";
import type { Site } from "../types";
import { ApiError } from "../api/client";

function SiteFormModal({ site, onClose, onSaved }: { site: Site | null; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(site?.name ?? "");
  const [address, setAddress] = useState(site?.address ?? "");
  const [timezone, setTimezone] = useState(site?.timezone ?? "UTC");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (site) {
        await sitesApi.updateSite(site.id, { name, address, timezone });
      } else {
        await sitesApi.createSite({ name, address, timezone });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save site");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <form onSubmit={handleSubmit} className="bg-base-900 border border-base-700 rounded-lg w-full max-w-md p-5 space-y-3">
        <h3 className="font-semibold text-slate-100 mb-2">{site ? "Edit Site" : "Add Site"}</h3>
        {error && <div className="text-sm text-severity-critical">{error}</div>}

        <div>
          <label className="block text-xs text-slate-400 mb-1">Name</label>
          <input required value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Address</label>
          <input value={address} onChange={(e) => setAddress(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Timezone</label>
          <input value={timezone} onChange={(e) => setTimezone(e.target.value)} placeholder="e.g. America/New_York" className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
            Cancel
          </button>
          <button type="submit" disabled={submitting} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50">
            {submitting ? "Saving..." : site ? "Save" : "Create Site"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function SitesPage() {
  const [sites, setSites] = useState<Site[]>([]);
  const [editingSite, setEditingSite] = useState<Site | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Site | null>(null);

  async function load() {
    try {
      setSites(await sitesApi.listSites());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sites");
    }
  }

  useEffect(() => {
    load();
  }, []);

  function openCreate() {
    setEditingSite(null);
    setShowModal(true);
  }

  function openEdit(site: Site) {
    setEditingSite(site);
    setShowModal(true);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    const id = deleteTarget.id;
    setDeleteTarget(null);
    setError(null);
    try {
      await sitesApi.deleteSite(id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete site");
    }
  }

  return (
    <Layout title="Sites">
      <div className="flex justify-between items-center mb-4">
        <div className="text-sm text-slate-400">{sites.length} site(s) configured</div>
        <button onClick={openCreate} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white">
          + Add Site
        </button>
      </div>

      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">Address</th>
              <th className="text-left px-4 py-2">Timezone</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {sites.map((site) => (
              <tr key={site.id}>
                <td className="px-4 py-2 text-slate-100">{site.name}</td>
                <td className="px-4 py-2 text-slate-400">{site.address || "—"}</td>
                <td className="px-4 py-2 text-slate-400">{site.timezone}</td>
                <td className="px-4 py-2 text-slate-400">{site.is_active ? "Active" : "Inactive"}</td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-3">
                    <button onClick={() => openEdit(site)} className="text-accent-500 hover:underline text-xs">
                      Edit
                    </button>
                    <button onClick={() => setDeleteTarget(site)} className="text-severity-critical hover:underline text-xs">
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {sites.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  No sites yet. Add one to organize cameras by location.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showModal && <SiteFormModal site={editingSite} onClose={() => setShowModal(false)} onSaved={load} />}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete site"
          message={`Delete "${deleteTarget.name}"? Cameras assigned to it will be unassigned, not deleted.`}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </Layout>
  );
}
