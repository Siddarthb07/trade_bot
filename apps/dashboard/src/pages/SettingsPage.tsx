import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../api";
import { saveHoldDisplayMode } from "../hooks/useHoldPrefs";

interface HoldSettings {
  hold_display_mode: "days" | "weeks" | "both";
  min_hold_days_filter: number;
  exit_reminders_enabled: boolean;
  theme_hold_multiplier: number;
  whatsapp_group_configured: boolean;
  dashboard_public_url: string;
}

export default function SettingsPage() {
  const [prefs, setPrefs] = useState<any>(null);
  const [hold, setHold] = useState<HoldSettings | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiFetch("/settings/alerts").then(setPrefs);
    apiFetch<HoldSettings>("/settings/hold").then(setHold);
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!prefs || !hold) return;
    await apiFetch("/settings/alerts", { method: "PATCH", body: JSON.stringify(prefs) });
    const updated = await apiFetch<HoldSettings>("/settings/hold", {
      method: "PATCH",
      body: JSON.stringify({
        hold_display_mode: hold.hold_display_mode,
        min_hold_days_filter: hold.min_hold_days_filter,
        exit_reminders_enabled: hold.exit_reminders_enabled,
        theme_hold_multiplier: hold.theme_hold_multiplier,
      }),
    });
    setHold(updated);
    saveHoldDisplayMode(updated.hold_display_mode);
    setSaved(true);
  }

  if (!prefs || !hold) return <p>Loading…</p>;

  return (
    <div className="settings-page">
      <section className="card">
        <h2>Settings</h2>
        <form onSubmit={onSubmit} className="settings-form">
          <h3>Alert preferences</h3>
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

          <h3>Hold & exit</h3>
          <label>Display format
            <select
              value={hold.hold_display_mode}
              onChange={(e) => setHold({ ...hold, hold_display_mode: e.target.value as HoldSettings["hold_display_mode"] })}
            >
              <option value="both">Days + weeks</option>
              <option value="days">Days only</option>
              <option value="weeks">Weeks only</option>
            </select>
          </label>
          <label>Minimum hold days (filter short picks)
            <input
              type="number"
              min={0}
              max={90}
              value={hold.min_hold_days_filter}
              onChange={(e) => setHold({ ...hold, min_hold_days_filter: Number(e.target.value) })}
            />
          </label>
          <label>Theme hold multiplier
            <input
              type="number"
              min={0.5}
              max={2}
              step={0.1}
              value={hold.theme_hold_multiplier}
              onChange={(e) => setHold({ ...hold, theme_hold_multiplier: Number(e.target.value) })}
            />
          </label>
          <label>
            <input
              type="checkbox"
              checked={hold.exit_reminders_enabled}
              onChange={(e) => setHold({ ...hold, exit_reminders_enabled: e.target.checked })}
            />
            {" "}Exit / review WhatsApp reminders
          </label>
          <p className="muted">WhatsApp group configured: <strong>{String(hold.whatsapp_group_configured)}</strong> (set <code>WHATSAPP_GROUP_ID</code> in .env)</p>

          <button type="submit">Save preferences</button>
          {saved && <p className="ok">Saved</p>}
        </form>
      </section>
    </div>
  );
}
