import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api";

const HOLD_PREFS_KEY = "tradebot_hold_prefs";

interface HoldPrefs {
  hold_display_mode: "days" | "weeks" | "both";
}

export default function SettingsPage() {
  const [prefs, setPrefs] = useState<any>(null);
  const [holdEnv, setHoldEnv] = useState<any>(null);
  const [holdLocal, setHoldLocal] = useState<HoldPrefs>({ hold_display_mode: "both" });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiFetch("/settings/alerts").then(setPrefs);
    apiFetch("/settings/hold").then(setHoldEnv);
    const raw = localStorage.getItem(HOLD_PREFS_KEY);
    if (raw) {
      try {
        setHoldLocal(JSON.parse(raw));
      } catch {
        /* ignore */
      }
    }
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    await apiFetch("/settings/alerts", { method: "PATCH", body: JSON.stringify(prefs) });
    localStorage.setItem(HOLD_PREFS_KEY, JSON.stringify(holdLocal));
    setSaved(true);
  }

  if (!prefs) return <p>Loading…</p>;

  return (
    <div className="settings-page">
      <section className="card">
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

          <h3>Hold & exit display (Phase 5)</h3>
          <label>Display format (browser)
            <select
              value={holdLocal.hold_display_mode}
              onChange={(e) => setHoldLocal({ hold_display_mode: e.target.value as HoldPrefs["hold_display_mode"] })}
            >
              <option value="both">Days + weeks</option>
              <option value="days">Days only</option>
              <option value="weeks">Weeks only</option>
            </select>
          </label>
          {holdEnv && (
            <>
              <p className="muted">Server exit reminders: <strong>{String(holdEnv.exit_reminders_enabled)}</strong> (set <code>EXIT_REMINDERS_ENABLED</code> in .env)</p>
              <p className="muted">WhatsApp group configured: <strong>{String(holdEnv.whatsapp_group_configured)}</strong> (set <code>WHATSAPP_GROUP_ID</code> in .env)</p>
              <p className="muted">Theme hold multiplier (server): <strong>{holdEnv.theme_hold_multiplier}</strong></p>
            </>
          )}

          <button type="submit">Save preferences</button>
          {saved && <p className="ok">Saved</p>}
        </form>
      </section>
    </div>
  );
}
