import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { StatCard } from "../components/ui/StatCard";
import { HorizontalBarChart } from "../components/ui/BarChart";
import * as storageApi from "../api/storage";
import type { StorageUsage } from "../types";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

export function StorageUsagePage() {
  const [usage, setUsage] = useState<StorageUsage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    storageApi
      .getStorageUsage()
      .then(setUsage)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load storage usage"));
  }, []);

  return (
    <Layout title="Storage Usage">
      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}

      {usage && (
        <>
          <div className="text-xs text-slate-500 mb-4">
            {usage.is_estimate
              ? "Estimated based on recorded file sizes — not a live query against the object-storage provider's billing API."
              : null}
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard label="Total Storage" value={formatBytes(usage.total_bytes)} />
            <StatCard label="Snapshots" value={formatBytes(usage.snapshot_bytes)} />
            <StatCard label="Evidence Clips" value={formatBytes(usage.evidence_clip_bytes)} />
            <StatCard label="Event Metadata" value={formatBytes(usage.event_metadata_bytes)} />
          </div>

          <div className="rounded-lg border border-base-700 bg-base-900 p-4">
            <div className="text-sm font-semibold text-slate-200 mb-3">Breakdown by category</div>
            <HorizontalBarChart
              data={[
                { label: "Snapshots", count: usage.snapshot_bytes, color: "#14b8a6" },
                { label: "Evidence Clips", count: usage.evidence_clip_bytes, color: "#f97316" },
                { label: "Cloud Recordings", count: usage.cloud_recording_bytes, color: "#3b82f6" },
                { label: "Continuous Recordings", count: usage.continuous_recording_bytes, color: "#8b5cf6" },
                { label: "Event Metadata (est.)", count: usage.event_metadata_bytes, color: "#64748b" },
              ]}
            />
          </div>

          <div className="text-xs text-slate-500 mt-4 space-y-1">
            <div>Cloud Recordings: {formatBytes(usage.cloud_recording_bytes)} (uploaded to MinIO/S3)</div>
            <div>Continuous Recordings: {formatBytes(usage.continuous_recording_bytes)} (local disk only)</div>
          </div>
        </>
      )}
    </Layout>
  );
}
