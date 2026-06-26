import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ReturnBarChart, TierPieChart } from "../components/Charts";
import StatCard from "../components/StatCard";
import { apiFetch, SignalItem } from "../api";
import { fmtExp, fmtPct, fmtValue, tierClass } from "../utils/format";

export default function BulkDealsPage() {
  const [items, setItems] = useState<SignalItem[]>([]);
  const [topPicks, setTopPicks] = useState<SignalItem[]>([]);
  const [market, setMarket] = useState("IN");
  const [tier, setTier] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const params = new URLSearchParams({ limit: "100" });
      if (market) params.set("market", market);
      if (tier) params.set("tier", tier);
      const bulkParams = new URLSearchParams(params);
      bulkParams.set("source", "nse_bulk");
      const blockParams = new URLSearchParams(params);
      blockParams.set("source", "nse_block");
      const [bulk, block, picks] = await Promise.all([
        apiFetch<{ items: SignalItem[] }>(`/signals?${bulkParams}`),
        apiFetch<{ items: SignalItem[] }>(`/signals?${blockParams}`),
        apiFetch<{ items: SignalItem[] }>(`/signals/top-picks?market=${market || "IN"}&limit=8`).catch(() => ({ items: [] })),
      ]);
      const merged = [...bulk.items, ...block.items].sort(
        (a, b) => new Date(b.disclosed_at).getTime() - new Date(a.disclosed_at).getTime(),
      );
      setItems(merged);
      setTopPicks(picks.items);
      setLoading(false);
    }
    load().catch(console.error);
  }, [market, tier]);

  const chartData = topPicks.map((s) => ({
    name: s.ticker,
    value: ((s.return_distribution?.expected_return_pct as number) || 0) * 100,
  }));

  const tierCounts = useMemo(() => {
    const c: Record<string, number> = {};
    items.forEach((s) => {
      const t = s.tier || "—";
      c[t] = (c[t] || 0) + 1;
    });
    return Object.entries(c).map(([name, value]) => ({ name, value }));
  }, [items]);

  return (
    <div className="page-stack">
      <section className="hero-banner bulk-hero">
        <div>
          <span className="eyebrow">NSE bulk & block deals</span>
          <h2>Smart-money bulk deals</h2>
          <p>Institutional buying from NSE bulk/block disclosures — ranked by estimated return.</p>
        </div>
        <div className="hero-stats">
          <StatCard label="Today's deals" value={String(items.length)} accent="blue" />
          <StatCard label="Top picks" value={String(topPicks.length)} sub="WhatsApp list" accent="amber" />
        </div>
      </section>

      <div className="grid-2">
        <section className="card chart-panel">
          <h3>Top bulk picks — est. return</h3>
          {loading ? <p>Loading…</p> : <ReturnBarChart data={chartData} color="#22d3ee" />}
        </section>
        <section className="card chart-panel">
          <h3>Deal tier mix</h3>
          {loading ? <p>Loading…</p> : <TierPieChart data={tierCounts} height={260} />}
        </section>
      </div>

      <div className="toolbar toolbar-card">
        <select value={market} onChange={(e) => setMarket(e.target.value)}>
          <option value="IN">India</option>
          <option value="US">US (SEC)</option>
        </select>
        <select value={tier} onChange={(e) => setTier(e.target.value)}>
          <option value="">All tiers</option>
          <option value="HIGH">HIGH</option>
          <option value="MEDIUM">MEDIUM</option>
          <option value="LOW">LOW</option>
        </select>
      </div>

      {topPicks.length > 0 && (
        <section className="card">
          <h3>Today&apos;s top bulk picks</h3>
          <div className="table-wrap">
            <table className="table table-modern">
              <thead>
                <tr><th>#</th><th>Ticker</th><th>Est.</th><th>Conf.</th><th>Investor</th><th>Tier</th></tr>
              </thead>
              <tbody>
                {topPicks.map((s, i) => (
                  <tr key={s.id}>
                    <td>{i + 1}</td>
                    <td><Link to={`/signals/${s.id}`}>{s.ticker}</Link></td>
                    <td className="ok">{fmtExp(s.return_distribution?.expected_return_pct as number)}</td>
                    <td>{fmtPct(s.calibrated_probability)}</td>
                    <td><Link to={`/entities/${encodeURIComponent(s.entity)}`}>{s.entity}</Link></td>
                    <td><span className={tierClass(s.tier)}>{s.tier}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card">
        <h3>All bulk & block deals</h3>
        {loading ? <p>Loading…</p> : (
          <div className="table-wrap">
            <table className="table table-modern">
              <thead>
                <tr>
                  <th>Date</th><th>Ticker</th><th>Investor</th><th>Deal</th><th>Est.</th><th>Conf.</th><th>Tier</th>
                </tr>
              </thead>
              <tbody>
                {items.map((s) => (
                  <tr key={s.id}>
                    <td>{new Date(s.disclosed_at).toLocaleDateString()}</td>
                    <td><Link to={`/signals/${s.id}`}>{s.ticker}</Link></td>
                    <td>{s.entity}</td>
                    <td>{fmtValue(s.value, s.market)}</td>
                    <td className="ok">{fmtExp(s.return_distribution?.expected_return_pct as number)}</td>
                    <td>{fmtPct(s.calibrated_probability)}</td>
                    <td><span className={tierClass(s.tier)}>{s.tier}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
