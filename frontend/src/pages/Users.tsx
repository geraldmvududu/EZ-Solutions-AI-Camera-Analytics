import { useEffect, useState, type FormEvent } from "react";
import { Layout } from "../components/layout/Layout";
import * as systemApi from "../api/system";
import type { UserItem } from "../types";
import { ApiError } from "../api/client";

const ROLES = ["VIEWER", "OPERATOR", "ADMIN", "SUPER_ADMIN"];

export function UsersPage() {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("VIEWER");
  const [error, setError] = useState<string | null>(null);

  function load() {
    systemApi
      .listUsers()
      .then(setUsers)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load users"));
  }

  useEffect(load, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await systemApi.createUser({ email, password, full_name: fullName, role });
      setShowForm(false);
      setEmail("");
      setFullName("");
      setPassword("");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create user");
    }
  }

  async function toggleActive(user: UserItem) {
    await systemApi.updateUser(user.id, { is_active: !user.is_active });
    load();
  }

  return (
    <Layout title="Users">
      <div className="flex justify-between items-center mb-4">
        <div className="text-sm text-slate-400">{users.length} user(s)</div>
        <button onClick={() => setShowForm(true)} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white">
          + Add User
        </button>
      </div>

      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Email</th>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">Role</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Last Login</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {users.map((u) => (
              <tr key={u.id}>
                <td className="px-4 py-2 text-slate-100">{u.email}</td>
                <td className="px-4 py-2 text-slate-400">{u.full_name}</td>
                <td className="px-4 py-2 text-slate-400">{u.role}</td>
                <td className="px-4 py-2 text-slate-400">{u.is_active ? "Active" : "Disabled"}</td>
                <td className="px-4 py-2 text-slate-500">{u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}</td>
                <td className="px-4 py-2">
                  <button onClick={() => toggleActive(u)} className="text-accent-500 hover:underline text-xs">
                    {u.is_active ? "Disable" : "Enable"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <form onSubmit={handleCreate} className="bg-base-900 border border-base-700 rounded-lg w-full max-w-md p-5 space-y-3">
            <h3 className="font-semibold text-slate-100 mb-2">Add User</h3>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Email</label>
              <input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Full Name</label>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Password</label>
              <input required type="password" minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Role</label>
              <select value={role} onChange={(e) => setRole(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowForm(false)} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
                Cancel
              </button>
              <button type="submit" className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white">
                Create
              </button>
            </div>
          </form>
        </div>
      )}
    </Layout>
  );
}
