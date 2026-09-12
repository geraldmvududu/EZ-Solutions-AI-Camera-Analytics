import { useEffect, useState } from "react";
import { Layout } from "../../components/layout/Layout";
import { StatCard } from "../../components/ui/StatCard";
import * as facesApi from "../../api/faces";
import type { FaceStatistics } from "../../types";

export function FaceDashboardPage() {
  const [stats, setStats] = useState<FaceStatistics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await facesApi.getFaceStatistics();
        if (!cancelled) setStats(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load statistics");
      }
    }
    load();
    const interval = setInterval(load, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <Layout title="Facial Recognition Dashboard">
      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      <div className="mb-4 text-xs text-slate-500 rounded-lg border border-base-700 bg-base-900 p-3">
        Recognition results are automated matches against enrolled biometric templates —
        treat "Recognized" as a candidate identification requiring appropriate verification
        in security-critical contexts, not definitive proof of identity. "Unknown" means no
        enrolled person matched; it is not itself evidence of wrongdoing.
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Recognized Today" value={stats.recognized_today} accent="success" />
          <StatCard label="Unknown Faces" value={stats.unknown_faces_today} accent={stats.unknown_faces_today > 0 ? "warning" : "default"} />
          <StatCard label="Active Alerts" value={stats.active_alerts} accent={stats.active_alerts > 0 ? "warning" : "default"} />
          <StatCard label="High Severity" value={stats.high_severity_active} accent={stats.high_severity_active > 0 ? "critical" : "default"} />
          <StatCard label="Violations Today" value={stats.violations_today} />
          <StatCard label="After-Hours Events" value={stats.after_hours_events_today} />
          <StatCard label="Restricted Area Events" value={stats.restricted_area_events_today} />
        </div>
      )}
    </Layout>
  );
}
