import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { getSystemHealth } from "../api/system";
import type { SystemHealth } from "../types";

const STATUS_COLOR: Record<string, string> = {
  HEALTHY: "text-accent-500",
  WARNING: "text-severity-medium",
  CRITICAL: "text-severity-critical",
};

export function SystemHealthPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);

  useEffect(() => {
    function load() {
      getSystemHealth().then(setHealth).catch(() => {});
    }
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  if (!health) {
    return (
      <Layout title="System Health">
        <div className="text-slate-500 text-sm">Loading...</div>
      </Layout>
    );
  }

  return (
    <Layout title="System Health">
      <div className={`text-lg font-semibold mb-6 ${STATUS_COLOR[health.overall_status]}`}>
        Overall status: {health.overall_status}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="rounded-lg border border-base-700 bg-base-900 p-4">
          <div className="text-xs text-slate-500 mb-1">CPU Usage</div>
          <div className="text-2xl font-bold text-slate-100">{health.cpu_percent.toFixed(1)}%</div>
        </div>
        <div className="rounded-lg border border-base-700 bg-base-900 p-4">
          <div className="text-xs text-slate-500 mb-1">RAM Usage</div>
          <div className="text-2xl font-bold text-slate-100">{health.ram_percent.toFixed(1)}%</div>
        </div>
        <div className="rounded-lg border border-base-700 bg-base-900 p-4">
          <div className="text-xs text-slate-500 mb-1">Disk Usage</div>
          <div className="text-2xl font-bold text-slate-100">{health.disk_percent.toFixed(1)}%</div>
        </div>
      </div>

      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Component</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Message</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {health.components.map((c) => (
              <tr key={c.component}>
                <td className="px-4 py-2 text-slate-100">{c.component}</td>
                <td className={`px-4 py-2 font-semibold ${STATUS_COLOR[c.status]}`}>{c.status}</td>
                <td className="px-4 py-2 text-slate-500">{c.message || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Layout>
  );
}
