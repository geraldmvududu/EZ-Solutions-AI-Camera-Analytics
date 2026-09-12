import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { StatCard } from "../components/ui/StatCard";
import { getIncidentSummary, type IncidentSummary } from "../api/misc";

const SEVERITY_ACCENT: Record<string, "critical" | "warning" | "default"> = {
  CRITICAL: "critical",
  HIGH: "critical",
  MEDIUM: "warning",
  LOW: "default",
  INFO: "default",
};

export function VideoIntelligenceDashboardPage() {
  const [summary, setSummary] = useState<IncidentSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await getIncidentSummary();
        if (!cancelled) setSummary(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load incident summary");
      }
    }
    load();
    const interval = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <Layout title="AI Video Intelligence">
      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      <div className="mb-4 text-xs text-slate-500 rounded-lg border border-base-700 bg-base-900 p-3">
        Gate-jumping/climbing detection is a real-time trajectory heuristic (not a trained classifier), and tailgating
        detection is video-only (no access-control-system integration exists in this platform) — every incident below
        is evidence-based and requires human review before being treated as confirmed. See the linked evidence on
        each incident.
      </div>

      <div className="mb-6">
        <div className="text-sm font-semibold text-slate-300 mb-2">Incidents (last 24h) by severity</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map((sev) => {
            const count = summary?.by_severity.find((s) => s.label === sev)?.count ?? 0;
            return <StatCard key={sev} label={sev} value={count} accent={SEVERITY_ACCENT[sev]} />;
          })}
        </div>
      </div>

      <div>
        <div className="text-sm font-semibold text-slate-300 mb-2">Incidents (last 24h) by category</div>
        <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-base-800 text-slate-400 text-xs uppercase">
              <tr>
                <th className="text-left px-4 py-2">Category</th>
                <th className="text-left px-4 py-2">Count</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-base-700">
              {(summary?.by_type ?? []).map((t) => (
                <tr key={t.label}>
                  <td className="px-4 py-2 text-slate-100">{t.label.replace(/_/g, " ")}</td>
                  <td className="px-4 py-2 text-slate-400">{t.count}</td>
                </tr>
              ))}
              {(!summary || summary.by_type.length === 0) && (
                <tr>
                  <td colSpan={2} className="px-4 py-8 text-center text-slate-500">
                    No categorized incidents in the last 24 hours.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Layout>
  );
}
