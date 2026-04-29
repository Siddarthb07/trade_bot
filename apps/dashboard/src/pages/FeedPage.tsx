import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, SignalItem } from "../api";

function fmtExp(s: SignalItem) {
  const exp = s.return_distribution?.expected_return_pct;
  if (exp == null) return "—";
  return `+${(exp * 100).toFixed(0)}%`;
}

export default function FeedPage() {
  const [items, setItems] = useState<SignalItem[]>([]);
  const [topPicks, setTopPicks] = useState<SignalItem[]>([]);
  const [market, setMarket] = useState("");
  const [tier, setTier] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const params = new URLSearchParams();
      if (market) params.set("market", market);
      if (tier) params.set("tier", tier);
      const [feed, picks] = await Promise.all([
        apiFetch<{ items: SignalItem[] }>(`/signals?${params.toString()}`),
        apiFetch<{ items: SignalItem[] }>("/signals/top-picks?market=IN&limit=5").catch(() => ({ items: [] })),
      ]);
      setItems(feed.items);
      setTopPicks(picks.items);
      setLoading(false);
    }
    load().catch(console.error);
  }, [market, tier]);

  return (
    <div>
      {topPicks.length > 0 && (
        <section className="card picks-banner">
          <h2>Today&apos;s top 5 picks (highest est. return)</h2>
          <p className="muted">Same list sent on WhatsApp at 7:30 PM IST</p>
          <table className="table">
            <thead>
              <tr><th>#</th><th>Ticker</th><th>Est. return</th><th>Conf.</th><th>Investor</th><th>Tier</th></tr>
            </thead>
            <tbody>
              {topPicks.map((s, i) => (
                <tr key={s.id}>
                  <td>{i + 1}</td>
                  <td><Link to={`/signals/${s.id}`}>{s.ticker}</Link></td>
                  <td className="ok">{fmtExp(s)}</td>
                  <td>{s.calibrated_probability != null ? `${(s.calibrated_probability * 100).toFixed(0)}%` : "—"}</td>
                  <td><Link to={`/entities/${encodeURIComponent(s.entity)}`}>{s.entity}</Link></td>
                  <td><span className={`tier ${s.tier?.toLowerCase()}`}>{s.tier}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <div className="toolbar">
        <select value={market} onChange={(e) => setMarket(e.target.value)}>
          <option value="">All markets</option>
          <option value="IN">India</option>
          <option value="US">US</option>
        </select>
        <select value={tier} onChange={(e) => setTier(e.target.value)}>
          <option value="">All tiers</option>
          <option value="HIGH">HIGH</option>
          <option value="MEDIUM">MEDIUM</option>
          <option value="LOW">LOW</option>
        </select>
      </div>
      {loading ? <p>Loading…</p> : (
        <table className="table">
          <thead>
            <tr>
              <th>Date</th><th>Market</th><th>Tier</th><th>Ticker</th><th>Entity</th><th>Action</th><th>Est.</th><th>Return</th><th>n</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.id}>
                <td>{new Date(s.disclosed_at).toLocaleDateString()}</td>
                <td>{s.market}</td>
                <td><span className={`tier ${s.tier?.toLowerCase()}`}>{s.tier || "—"}</span></td>
                <td><Link to={`/signals/${s.id}`}>{s.ticker}</Link></td>
                <td><Link to={`/entities/${encodeURIComponent(s.entity)}`}>{s.entity}</Link></td>
                <td>{s.action}</td>
                <td>{s.calibrated_probability != null ? `${(s.calibrated_probability * 100).toFixed(0)}%` : "—"}</td>
                <td>{fmtExp(s)}</td>
                <td>{s.n_trades ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
