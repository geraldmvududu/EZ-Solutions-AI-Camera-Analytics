import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { StatCard } from "../components/ui/StatCard";
import { getDashboardStats, getSystemHealth } from "../api/system";
import { listEvents, listAlerts } from "../api/events";
import type { AlertItem, DashboardStats, EventItem, SystemHealth } from "../types";
import { SeverityBadge } from "../components/ui/Badge";

function formatBytes(bytes: number): string {
  if (!bytes) return "0 GB";
  const gb = bytes / 1024 ** 3;
  return `${gb.toFixed(1)} GB`;
}

export function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [recentEvents, setRecentEvents] = useState<EventItem[]>([]);
  const [recentAlerts, setRecentAlerts] = useState<AlertItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [statsRes, healthRes, eventsRes, alertsRes] = await Promise.all([
          getDashboardStats(),
          getSystemHealth(),
          listEvents({ limit: "10" }),
          listAlerts({ limit: "10" }),
        ]);
        if (cancelled) return;
        setStats(statsRes);
        setHealth(healthRes);
        setRecentEvents(eventsRes);
        setRecentAlerts(alertsRes);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load dashboard data");
      }
    }

    load();
    const interval = setInterval(load, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <Layout title="Dashboard">
      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      {stats && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-4 mb-6">
            <StatCard label="Total Cameras" value={stats.total_cameras} />
            <StatCard label="Online Cameras" value={stats.online_cameras} accent="success" />
            <StatCard label="Offline Cameras" value={stats.offline_cameras} accent={stats.offline_cameras > 0 ? "warning" : "default"} />
            <StatCard label="Active Alerts" value={stats.active_alerts} accent={stats.active_alerts > 0 ? "warning" : "default"} />
            <StatCard label="Critical Alerts" value={stats.critical_alerts} accent={stats.critical_alerts > 0 ? "critical" : "default"} />
            <StatCard label="Events Today" value={stats.events_today} />
            <StatCard label="People Detected" value={stats.people_detected_today} />
            <StatCard label="Vehicles Detected" value={stats.vehicles_detected_today} />
            <StatCard label="Motion Events" value={stats.motion_events_today} />
            <StatCard label="AI Events" value={stats.ai_events_today} />
            <StatCard label="Recording Cameras" value={stats.recording_cameras} />
            <StatCard label="Storage Used" value={`${formatBytes(stats.storage_used_bytes)} / ${formatBytes(stats.storage_total_bytes)}`} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <StatCard label="CPU" value={`${stats.cpu_percent.toFixed(0)}%`} />
            <StatCard label="RAM" value={`${stats.ram_percent.toFixed(0)}%`} />
            <StatCard label="AI Processing" value={stats.ai_processing_device.toUpperCase()} />
          </div>
        </>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-lg border border-base-700 bg-base-900">
          <div className="px-4 py-3 border-b border-base-700 font-semibold text-slate-200 text-sm">Recent Events</div>
          <div className="divide-y divide-base-700">
            {recentEvents.length === 0 && <div className="p-4 text-sm text-slate-500">No events yet.</div>}
            {recentEvents.map((e) => (
              <div key={e.id} className="px-4 py-3 flex items-center justify-between text-sm">
                <div>
                  <div className="text-slate-200">{e.event_type.replace(/_/g, " ")}</div>
                  <div className="text-xs text-slate-500">{new Date(e.occurred_at).toLocaleString()}</div>
                </div>
                <SeverityBadge severity={e.severity} />
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-base-700 bg-base-900">
          <div className="px-4 py-3 border-b border-base-700 font-semibold text-slate-200 text-sm">Recent Alerts</div>
          <div className="divide-y divide-base-700">
            {recentAlerts.length === 0 && <div className="p-4 text-sm text-slate-500">No alerts yet.</div>}
            {recentAlerts.map((a) => (
              <div key={a.id} className="px-4 py-3 flex items-center justify-between text-sm">
                <div>
                  <div className="text-slate-200">{a.alert_type.replace(/_/g, " ")}</div>
                  <div className="text-xs text-slate-500">{new Date(a.created_at).toLocaleString()}</div>
                </div>
                <SeverityBadge severity={a.severity} />
              </div>
            ))}
          </div>
        </div>
      </div>

      {health && health.overall_status !== "HEALTHY" && (
        <div className="mt-6 rounded-lg border border-severity-medium/40 bg-severity-medium/10 p-4 text-sm text-severity-medium">
          System status: {health.overall_status} —{" "}
          {health.components.filter((c) => c.status !== "HEALTHY").map((c) => `${c.component}: ${c.status}`).join(", ")}
        </div>
      )}
    </Layout>
  );
}
