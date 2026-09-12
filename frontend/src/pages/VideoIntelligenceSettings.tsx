import { useEffect, useState } from "react";
import { Layout } from "../components/layout/Layout";
import { getVideoIntelligenceSettings, updateVideoIntelligenceSettings, type VideoIntelligenceSettings } from "../api/misc";

export function VideoIntelligenceSettingsPage() {
  const [settings, setSettings] = useState<VideoIntelligenceSettings | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    getVideoIntelligenceSettings().then(setSettings).catch((err) => setError(err instanceof Error ? err.message : "Failed to load settings"));
  }, []);

  async function handleSave() {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await updateVideoIntelligenceSettings(settings);
      setSettings(updated);
      setSavedAt(Date.now());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  if (!settings) {
    return (
      <Layout title="AI Video Intelligence Settings">
        {error && <div className="text-severity-critical text-sm">{error}</div>}
      </Layout>
    );
  }

  return (
    <Layout title="AI Video Intelligence Settings">
      <div className="max-w-2xl space-y-6">
        {error && <div className="text-severity-critical text-sm">{error}</div>}

        <div className="rounded-lg border border-base-700 bg-base-900 p-4 space-y-3">
          <div className="font-semibold text-slate-200 text-sm">Detection categories</div>
          <p className="text-xs text-slate-500">
            Each category also requires opting in per-tripwire/zone (Zones &amp; Tripwires page) — these are a
            tenant-wide kill switch on top of that.
          </p>
          {([
            ["gate_jumping_enabled", "Gate jump / climbing detection"],
            ["tailgating_enabled", "Tailgating detection"],
            ["restricted_area_enabled", "Restricted area detection"],
          ] as const).map(([field, label]) => (
            <label key={field} className="flex items-center gap-2 text-sm text-slate-300">
              <input
                type="checkbox"
                checked={settings[field]}
                onChange={(e) => setSettings({ ...settings, [field]: e.target.checked })}
              />
              {label}
            </label>
          ))}

          <div className="pt-2 space-y-2 opacity-50">
            <div className="text-xs text-slate-500">Coming soon (needs a multi-class object detector / pose estimation — see documented limitations):</div>
            <label className="flex items-center gap-2 text-sm text-slate-400">
              <input type="checkbox" disabled />
              Potential theft / unauthorized object removal
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-400">
              <input type="checkbox" disabled />
              Abandoned object detection
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-400">
              <input type="checkbox" disabled />
              Person falling / safety detection
            </label>
            <label className="flex items-center gap-2 text-sm text-slate-400">
              <input type="checkbox" disabled />
              PPE detection
            </label>
          </div>
        </div>

        <div className="rounded-lg border border-base-700 bg-base-900 p-4 space-y-3">
          <div className="font-semibold text-slate-200 text-sm">Evidence clips</div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Pre-event seconds</label>
              <input
                type="number"
                min={0}
                value={settings.pre_event_seconds}
                onChange={(e) => setSettings({ ...settings, pre_event_seconds: Number(e.target.value) })}
                className="w-full rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Post-event seconds</label>
              <input
                type="number"
                min={0}
                value={settings.post_event_seconds}
                onChange={(e) => setSettings({ ...settings, post_event_seconds: Number(e.target.value) })}
                className="w-full rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100"
              />
            </div>
          </div>
          <p className="text-xs text-slate-500">
            Available pre-roll is capped by how early the underlying recording segment itself started — there is no
            live ring buffer independent of recording segments.
          </p>
        </div>

        <div className="rounded-lg border border-base-700 bg-base-900 p-4 space-y-3">
          <div className="font-semibold text-slate-200 text-sm">Risk score / business hours</div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Business hours start</label>
              <input
                type="time"
                value={settings.business_hours_start}
                onChange={(e) => setSettings({ ...settings, business_hours_start: e.target.value })}
                className="w-full rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Business hours end</label>
              <input
                type="time"
                value={settings.business_hours_end}
                onChange={(e) => setSettings({ ...settings, business_hours_end: e.target.value })}
                className="w-full rounded bg-base-800 border border-base-600 px-2 py-1.5 text-sm text-slate-100"
              />
            </div>
          </div>
          <p className="text-xs text-slate-500">
            Used only to compute an incident's risk score's after-hours bonus (alert prioritization) — not a proof of
            wrongdoing, and independent of any per-rule time window configured in the Rules page.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button onClick={handleSave} disabled={saving} className="px-4 py-2 text-sm rounded bg-accent-600 hover:bg-accent-500 text-white disabled:opacity-50">
            {saving ? "Saving..." : "Save Settings"}
          </button>
          {savedAt && <span className="text-xs text-slate-500">Saved.</span>}
        </div>
      </div>
    </Layout>
  );
}
