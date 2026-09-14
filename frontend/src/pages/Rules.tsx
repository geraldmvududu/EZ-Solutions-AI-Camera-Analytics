import { useEffect, useState, type FormEvent } from "react";
import { Layout } from "../components/layout/Layout";
import { SeverityBadge } from "../components/ui/Badge";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import * as rulesApi from "../api/misc";
import type { AIRule } from "../api/misc";

const EVENT_TYPES = ["PERSON_DETECTED", "VEHICLE_DETECTED", "MOTION_DETECTED", "TRIPWIRE_VIOLATION", "INTRUSION_DETECTED", "LOITERING_DETECTED"];
const SEVERITIES = ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"];

function RuleFormModal({ rule, onClose, onSaved }: { rule: AIRule | null; onClose: () => void; onSaved: () => void }) {
  const existingEventType = typeof rule?.conditions.event_type === "string" ? rule.conditions.event_type : "PERSON_DETECTED";
  const [name, setName] = useState(rule?.name ?? "");
  const [eventType, setEventType] = useState(existingEventType);
  const [severity, setSeverity] = useState(rule?.action_severity ?? "HIGH");
  const [isEnabled, setIsEnabled] = useState(rule?.is_enabled ?? true);
  const [cooldownSeconds, setCooldownSeconds] = useState(rule?.cooldown_seconds ?? 300);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      if (rule) {
        await rulesApi.updateRule(rule.id, {
          name,
          conditions: { event_type: eventType },
          action_severity: severity,
          is_enabled: isEnabled,
          cooldown_seconds: cooldownSeconds,
        });
      } else {
        await rulesApi.createRule({
          name,
          conditions: { event_type: eventType },
          action_severity: severity,
          action_alert_type: eventType,
          cooldown_seconds: cooldownSeconds,
        });
      }
      onSaved();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save rule");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <form onSubmit={handleSubmit} className="bg-base-900 border border-base-700 rounded-lg w-full max-w-md p-5 space-y-3">
        <h3 className="font-semibold text-slate-100 mb-2">{rule ? "Edit Rule" : "Add Rule"}</h3>
        {error && <div className="text-sm text-severity-critical">{error}</div>}

        <div>
          <label className="block text-xs text-slate-400 mb-1">Name</label>
          <input required value={name} onChange={(e) => setName(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100" />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Trigger event type</label>
          <select value={eventType} onChange={(e) => setEventType(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
            {EVENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Alert severity</label>
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100">
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">Cooldown between alerts (seconds)</label>
          <input
            type="number" min={0} step={1} value={cooldownSeconds}
            onChange={(e) => setCooldownSeconds(Number(e.target.value))}
            className="w-full rounded bg-base-800 border border-base-600 px-3 py-1.5 text-sm text-slate-100"
          />
          <p className="text-xs text-slate-500 mt-1">
            While this rule keeps matching new events, it won't create another alert until this many seconds have
            passed since its last one (default 300 = 5 min). Set to 0 to alert on every single match.
          </p>
        </div>
        {rule && (
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input type="checkbox" checked={isEnabled} onChange={(e) => setIsEnabled(e.target.checked)} />
            Enabled
          </label>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-3 py-1.5 text-sm rounded border border-base-600 text-slate-300">
            Cancel
          </button>
          <button type="submit" disabled={submitting} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50">
            {submitting ? "Saving..." : rule ? "Save" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}

export function RulesPage() {
  const [rules, setRules] = useState<AIRule[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [editingRule, setEditingRule] = useState<AIRule | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AIRule | null>(null);

  function load() {
    rulesApi.listRules().then(setRules).catch(() => {});
  }

  useEffect(load, []);

  function openCreate() {
    setEditingRule(null);
    setShowForm(true);
  }

  function openEdit(rule: AIRule) {
    setEditingRule(rule);
    setShowForm(true);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    await rulesApi.deleteRule(deleteTarget.id);
    setDeleteTarget(null);
    load();
  }

  return (
    <Layout title="Rules">
      <div className="flex justify-between items-center mb-4">
        <div className="text-sm text-slate-400">{rules.length} rule(s) configured</div>
        <button onClick={openCreate} className="px-3 py-1.5 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white">
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
              <th className="text-left px-4 py-2">Cooldown</th>
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
                <td className="px-4 py-2 text-slate-400">{r.cooldown_seconds === 0 ? "None" : `${r.cooldown_seconds}s`}</td>
                <td className="px-4 py-2 text-slate-400">{r.is_enabled ? "Yes" : "No"}</td>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-3">
                    <button onClick={() => openEdit(r)} className="text-accent-500 hover:underline text-xs">
                      Edit
                    </button>
                    <button onClick={() => setDeleteTarget(r)} className="text-severity-critical hover:underline text-xs">
                      Delete
                    </button>
                  </div>
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

      {showForm && <RuleFormModal rule={editingRule} onClose={() => setShowForm(false)} onSaved={load} />}

      {deleteTarget && (
        <ConfirmDialog
          title="Delete rule"
          message={`Delete "${deleteTarget.name}"? Alerts it already created are kept; it will simply stop matching new events.`}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </Layout>
  );
}
