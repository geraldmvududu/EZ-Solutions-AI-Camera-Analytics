import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { SeverityBadge, StatusBadge } from "../components/ui/Badge";
import { listAlerts, updateAlert } from "../api/events";
import { useLiveFeed } from "../hooks/useLiveFeed";
import type { AlertItem } from "../types";
import { useAuth } from "../context/AuthContext";

export function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const { hasPermission } = useAuth();

  function load() {
    listAlerts({ limit: "200" })
      .then(setAlerts)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load alerts"));
  }

  useEffect(load, []);

  useLiveFeed((message) => {
    if (message.type === "alert") setAlerts((prev) => [message.alert, ...prev]);
  }, true);

  async function handleStatusChange(id: string, status: string) {
    await updateAlert(id, { status });
    load();
  }

  const canManage = hasPermission("manage_alerts");

  return (
    <Layout title="Alerts">
      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}
      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-left px-4 py-2">Severity</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Created</th>
              {canManage && <th className="text-left px-4 py-2">Actions</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {alerts.map((a) => (
              <tr key={a.id}>
                <td className="px-4 py-2 text-slate-100">{a.alert_type.replace(/_/g, " ")}</td>
                <td className="px-4 py-2">
                  <SeverityBadge severity={a.severity} />
                </td>
                <td className="px-4 py-2">
                  <StatusBadge status={a.status} />
                </td>
                <td className="px-4 py-2 text-slate-500">{new Date(a.created_at).toLocaleString()}</td>
                {canManage && (
                  <td className="px-4 py-2">
                    <select
                      value={a.status}
                      onChange={(e) => handleStatusChange(a.id, e.target.value)}
                      className="rounded bg-base-800 border border-base-600 px-2 py-1 text-xs text-slate-100"
                    >
                      {["NEW", "ACKNOWLEDGED", "INVESTIGATING", "RESOLVED", "FALSE_POSITIVE"].map((s) => (
                        <option key={s} value={s}>
                          {s}
                        </option>
                      ))}
                    </select>
                  </td>
                )}
              </tr>
            ))}
            {alerts.length === 0 && (
              <tr>
                <td colSpan={canManage ? 5 : 4} className="px-4 py-8 text-center text-slate-500">
                  No alerts yet. Alerts are generated automatically when a security rule matches a real event.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Layout>
  );
}
