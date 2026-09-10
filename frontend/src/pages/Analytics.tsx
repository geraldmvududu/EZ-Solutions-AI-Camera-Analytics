import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { StatCard } from "../components/ui/StatCard";
import { HorizontalBarChart, HourlyBarChart } from "../components/ui/BarChart";
import * as analyticsApi from "../api/analytics";
import type { AnalyticsSummary } from "../api/analytics";

const SEVERITY_COLORS: Record<string, string> = {
  INFO: "#3b82f6",
  LOW: "#22c55e",
  MEDIUM: "#eab308",
  HIGH: "#f97316",
  CRITICAL: "#ef4444",
};

function formatBytes(bytes: number): string {
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function toDateInputValue(isoDaysAgo: number): string {
  const d = new Date();
  d.setDate(d.getDate() - isoDaysAgo);
  return d.toISOString().slice(0, 10);
}

export function AnalyticsPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState(toDateInputValue(7));
  const [endDate, setEndDate] = useState(toDateInputValue(0));
  const [downloading, setDownloading] = useState<string | null>(null);

  function load() {
    const params: Record<string, string> = {};
    if (startDate) params.start = new Date(startDate + "T00:00:00Z").toISOString();
    if (endDate) params.end = new Date(endDate + "T23:59:59Z").toISOString();
    analyticsApi
      .getAnalyticsSummary(params)
      .then(setSummary)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load analytics"));
  }

  useEffect(load, [startDate, endDate]);

  async function handleDownload(kind: "events" | "alerts" | "pdf") {
    setDownloading(kind);
    const params: Record<string, string> = {};
    if (startDate) params.start = new Date(startDate + "T00:00:00Z").toISOString();
    if (endDate) params.end = new Date(endDate + "T23:59:59Z").toISOString();
    try {
      if (kind === "events") await analyticsApi.downloadEventsCsv(params);
      else if (kind === "alerts") await analyticsApi.downloadAlertsCsv(params);
      else await analyticsApi.downloadSecurityReportPdf(params);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloading(null);
    }
  }

  return (
    <Layout title="AI Analytics">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div className="flex items-end gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">From</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">To</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100"
            />
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => handleDownload("events")}
            disabled={downloading !== null}
            className="px-3 py-1.5 text-xs rounded border border-base-600 text-slate-300 hover:bg-base-800 disabled:opacity-50"
          >
            {downloading === "events" ? "Downloading…" : "Export Events CSV"}
          </button>
          <button
            onClick={() => handleDownload("alerts")}
            disabled={downloading !== null}
            className="px-3 py-1.5 text-xs rounded border border-base-600 text-slate-300 hover:bg-base-800 disabled:opacity-50"
          >
            {downloading === "alerts" ? "Downloading…" : "Export Alerts CSV"}
          </button>
          <button
            onClick={() => handleDownload("pdf")}
            disabled={downloading !== null}
            className="px-3 py-1.5 text-xs rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50"
          >
            {downloading === "pdf" ? "Generating…" : "Download PDF Report"}
          </button>
        </div>
      </div>

      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      {summary && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard label="Total Events" value={summary.total_events} />
            <StatCard label="Total Alerts" value={summary.total_alerts} />
            <StatCard label="Total Detections" value={summary.total_detections} />
            <StatCard label="Storage Used" value={`${formatBytes(summary.storage_used_bytes)} / ${formatBytes(summary.storage_total_bytes)}`} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <div className="rounded-lg border border-base-700 bg-base-900 p-4">
              <div className="font-semibold text-slate-200 text-sm mb-3">Events by Hour of Day</div>
              <HourlyBarChart data={summary.events_by_hour} />
            </div>

            <div className="rounded-lg border border-base-700 bg-base-900 p-4">
              <div className="font-semibold text-slate-200 text-sm mb-3">Most Active Cameras</div>
              <HorizontalBarChart data={summary.most_active_cameras.map((c) => ({ label: c.label, count: c.count }))} />
            </div>

            <div className="rounded-lg border border-base-700 bg-base-900 p-4">
              <div className="font-semibold text-slate-200 text-sm mb-3">Alerts by Severity</div>
              <HorizontalBarChart
                data={summary.alerts_by_severity.map((c) => ({ label: c.label, count: c.count, color: SEVERITY_COLORS[c.label] }))}
              />
            </div>

            <div className="rounded-lg border border-base-700 bg-base-900 p-4">
              <div className="font-semibold text-slate-200 text-sm mb-3">Detections by Object Type</div>
              <HorizontalBarChart data={summary.detections_by_object_type.map((c) => ({ label: c.label, count: c.count }))} />
            </div>

            <div className="rounded-lg border border-base-700 bg-base-900 p-4">
              <div className="font-semibold text-slate-200 text-sm mb-3">Events by Camera</div>
              <HorizontalBarChart data={summary.events_by_camera.map((c) => ({ label: c.label, count: c.count }))} />
            </div>

            <div className="rounded-lg border border-base-700 bg-base-900 p-4">
              <div className="font-semibold text-slate-200 text-sm mb-3">Camera Status</div>
              <HorizontalBarChart
                data={summary.camera_status_summary.map((c) => ({
                  label: c.label,
                  count: c.count,
                  color: c.label === "ONLINE" ? "#14b8a6" : c.label === "ERROR" ? "#ef4444" : "#5a6472",
                }))}
              />
            </div>
          </div>
        </>
      )}
    </Layout>
  );
}
