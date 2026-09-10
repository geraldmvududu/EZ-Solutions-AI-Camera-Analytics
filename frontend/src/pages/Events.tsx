import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { SeverityBadge } from "../components/ui/Badge";
import { listEvents } from "../api/events";
import type { EventItem } from "../types";

export function EventsPage() {
  const [events, setEvents] = useState<EventItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listEvents({ limit: "200" })
      .then(setEvents)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load events"));
  }, []);

  return (
    <Layout title="Events">
      {error && <div className="text-severity-critical text-sm mb-4">{error}</div>}
      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Type</th>
              <th className="text-left px-4 py-2">Severity</th>
              <th className="text-left px-4 py-2">Description</th>
              <th className="text-left px-4 py-2">Occurred</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {events.map((e) => (
              <tr key={e.id}>
                <td className="px-4 py-2 text-slate-100">{e.event_type.replace(/_/g, " ")}</td>
                <td className="px-4 py-2">
                  <SeverityBadge severity={e.severity} />
                </td>
                <td className="px-4 py-2 text-slate-400">{e.description || "—"}</td>
                <td className="px-4 py-2 text-slate-500">{new Date(e.occurred_at).toLocaleString()}</td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-slate-500">
                  No events recorded yet. Events appear here once the AI engine (Phase 3) is processing camera feeds.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Layout>
  );
}
