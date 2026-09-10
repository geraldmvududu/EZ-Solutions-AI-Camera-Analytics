import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { listAuditLogs, type AuditLogEntry } from "../api/system";

export function AuditLogsPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAuditLogs()
      .then(setLogs)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load audit logs"));
  }, []);

  return (
    <Layout title="Audit Logs">
      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}
      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Action</th>
              <th className="text-left px-4 py-2">Resource</th>
              <th className="text-left px-4 py-2">Result</th>
              <th className="text-left px-4 py-2">IP</th>
              <th className="text-left px-4 py-2">Timestamp</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {logs.map((log) => (
              <tr key={log.id}>
                <td className="px-4 py-2 text-slate-100">{log.action}</td>
                <td className="px-4 py-2 text-slate-400">
                  {log.resource_type} {log.resource_id ? `#${log.resource_id.slice(0, 8)}` : ""}
                </td>
                <td className={`px-4 py-2 ${log.result === "SUCCESS" ? "text-accent-500" : "text-severity-critical"}`}>{log.result}</td>
                <td className="px-4 py-2 text-slate-500">{log.ip_address || "—"}</td>
                <td className="px-4 py-2 text-slate-500">{new Date(log.created_at).toLocaleString()}</td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  No audit entries yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Layout>
  );
}
