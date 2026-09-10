import { useEffect, useState, type FormEvent } from "react";
import { Layout } from "../components/layout/Layout";
import { SeverityBadge } from "../components/ui/Badge";
import * as rulesApi from "../api/misc";
import type { AIRule } from "../api/misc";

export function RulesPage() {
  const [rules, setRules] = useState<AIRule[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [eventType, setEventType] = useState("PERSON_DETECTED");
  const [severity, setSeverity] = useState("HIGH");

  function load() {
    rulesApi.listRules().then(setRules).catch(() => {});
  }

  useEffect(load, []);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    await rulesApi.createRule({
      name,
      conditions: { event_type: eventType },
      action_severity: severity,
      action_alert_type: "RULE_MATCH",
    });
    setShowForm(false);
    setName("");
    load();
  }

  async function handleDelete(id: string) {
    await rulesApi.deleteRule(id);
    load();
  }

  return (
    <Layout title="Rules">
      <div className="flex justify-between items-center mb-4">
        <div className="text-sm text-slate-400">{rules.length} rule(s) configured</div>
        <button onClick={() => setShowForm(true)} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white">
          + Add Rule
        </button>
      </div>

      <div className="rounded-lg border border-base-700 bg-base-900 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-base-800 text-slate-400 text-xs uppercase">
            <tr>
              <th className="text-left px-4 py-2">Name</th>
              <th className="text-left px-4 py-2">Condition</th>
              <th className="text-left px-4 py-2">Alert Severity</th>
              <th className="text-left px-4 py-2">Enabled</th>
              <th className="text-left px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-base-700">
            {rules.map((r) => (
              <tr key={r.id}>
                <td className="px-4 py-2 text-slate-100">{r.name}</td>
                <td className="px-4 py-2 text-slate-400 font-mono text-xs">{JSON.stringify(r.conditions)}</td>
                <td className="px-4 py-2">
                  <SeverityBadge severity={r.action_severity} />
                </td>
                <td className="px-4 py-2 text-slate-400">{r.is_enabled ? "Yes" : "No"}</td>
                <td className="px-4 py-2">
                  <button onClick={() => handleDelete(r.id)} className="text-severity-critical hover:underline text-xs">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {rules.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                  No rules yet. Rules evaluate every real incoming event and generate an Alert when matched.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <form onSubmit={handleCreate} className="bg-base-900 border border-base-700 rounded-lg w-full max-w-md p-5 space-y-3">
            <h3 className="font-semibold text-slate-100 mb-2">Add Rule</h3>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Name</label>
              <input required value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Trigger event type</label>
              <select value={eventType} onChange={(e) => setEventType(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
                {["PERSON_DETECTED", "VEHICLE_DETECTED", "MOTION_DETECTED", "TRIPWIRE_VIOLATION", "INTRUSION_DETECTED", "LOITERING_DETECTED"].map((t) => (
                  <option key={t} value={t}>
                    {t.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Alert severity</label>
              <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
                {["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"].map((s) => (
                  <option key={s} value={s}>
                    {s}
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
