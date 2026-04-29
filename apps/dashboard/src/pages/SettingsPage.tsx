import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api";

export default function SettingsPage() {
  const [prefs, setPrefs] = useState<any>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiFetch("/settings/alerts").then(setPrefs);
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    await apiFetch("/settings/alerts", { method: "PATCH", body: JSON.stringify(prefs) });
    setSaved(true);
  }

  if (!prefs) return <p>Loading…</p>;

  return (
    <div className="card">
      <h2>Alert Settings</h2>
      <form onSubmit={onSubmit} className="settings-form">
        <label>Min tier
          <select value={prefs.min_tier} onChange={(e) => setPrefs({ ...prefs, min_tier: e.target.value })}>
            <option value="HIGH">HIGH only</option>
            <option value="MEDIUM">MEDIUM+</option>
          </select>
        </label>
        <label>Quiet hours start<input type="number" min={0} max={23} value={prefs.quiet_hours_start} onChange={(e) => setPrefs({ ...prefs, quiet_hours_start: Number(e.target.value) })} /></label>
        <label>Quiet hours end<input type="number" min={0} max={23} value={prefs.quiet_hours_end} onChange={(e) => setPrefs({ ...prefs, quiet_hours_end: Number(e.target.value) })} /></label>
        <label><input type="checkbox" checked={prefs.market_in} onChange={(e) => setPrefs({ ...prefs, market_in: e.target.checked })} /> India alerts</label>
        <label><input type="checkbox" checked={prefs.market_us} onChange={(e) => setPrefs({ ...prefs, market_us: e.target.checked })} /> US alerts</label>
        <p>Dashboard URL for phone links: <code>{prefs.dashboard_public_url}</code></p>
        <p>Global alerts enabled (env): <strong>{String(prefs.alerts_enabled)}</strong></p>
        <button type="submit">Save preferences</button>
        {saved && <p className="ok">Saved</p>}
      </form>
    </div>
  );
}
