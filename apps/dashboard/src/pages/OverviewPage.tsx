import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { HeatBarChart, ReturnBarChart } from "../components/Charts";
import StatCard from "../components/StatCard";
import { apiFetch, LiveThemePick, SignalItem, ThemeSummary } from "../api";
import { fmtExp, fmtPct, tierClass } from "../utils/format";

export default function OverviewPage() {
  const [bulkPicks, setBulkPicks] = useState<SignalItem[]>([]);
  const [demandPicks, setDemandPicks] = useState<LiveThemePick[]>([]);
  const [themes, setThemes] = useState<ThemeSummary[]>([]);
  const [signalCount, setSignalCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const [bulk, demand, themeData, allSignals] = await Promise.all([
        apiFetch<{ items: SignalItem[] }>("/signals/top-picks?market=IN&limit=5").catch(() => ({ items: [] })),
        apiFetch<{ items: LiveThemePick[] }>("/themes/live-picks?limit=8&no_bulk_only=true"),
        apiFetch<{ themes: ThemeSummary[] }>("/themes"),
        apiFetch<{ total: number }>("/signals?limit=1").catch(() => ({ total: 0 })),
      ]);
      setBulkPicks(bulk.items);
      setDemandPicks(demand.items);
      setThemes(themeData.themes);
      setSignalCount(allSignals.total || 0);
      setLoading(false);
    }
    load().catch(console.error);
  }, []);

  const bulkChart = bulkPicks.map((s) => ({
    name: s.ticker,
    value: ((s.return_distribution?.expected_return_pct as number) || 0) * 100,
  }));

  const demandChart = demandPicks.slice(0, 6).map((p) => ({
    name: p.ticker,
    value: (p.expected_return_pct || 0) * 100,
  }));

  const heatData = themes.slice(0, 7).map((t) => ({
    name: t.name.split(" ")[0],
    heat: Math.round((t.theme_heat || 0) * 100),
  }));

  return (
    <div className="page-stack">
      <section className="hero-banner overview-hero">
        <div>
          <span className="eyebrow">Dashboard</span>
          <h2>Today at a glance</h2>
          <p>Bulk smart-money deals and demand-driven predictions in one view.</p>
        </div>
        <div className="hero-stats">
          <StatCard label="Signals tracked" value={loading ? "…" : String(signalCount)} accent="blue" />
          <StatCard label="Demand picks" value={loading ? "…" : String(demandPicks.length)} sub="no bulk needed" accent="purple" />
          <StatCard label="Bulk top 5" value={loading ? "…" : String(bulkPicks.length)} sub="NSE today" accent="green" />
        </div>
      </section>

      <div className="tab-cards">
        <Link to="/demand" className="tab-card tab-card-purple">
          <h3>🌍 Demand Picks</h3>
          <p>AI storage, defense, power — stocks predicted from world trends</p>
          <span className="tab-card-cta">{demandPicks.length} live picks →</span>
        </Link>
        <Link to="/bulk" className="tab-card tab-card-blue">
          <h3>📊 Bulk Deals</h3>
          <p>NSE institutional buying with smart-money scoring</p>
          <span className="tab-card-cta">{bulkPicks.length} top picks →</span>
        </Link>
        <Link to="/themes" className="tab-card tab-card-cyan">
          <h3>🔥 Theme Explorer</h3>
          <p>Deep dive into each demand sector with charts</p>
          <span className="tab-card-cta">{themes.length} themes →</span>
        </Link>
      </div>

      <div className="grid-2">
        <section className="card chart-panel">
          <div className="panel-head">
            <h3>Demand picks — est. return</h3>
            <Link to="/demand" className="link-sm">See all →</Link>
          </div>
          {loading ? <p>Loading…</p> : <ReturnBarChart data={demandChart} height={260} color="#a78bfa" />}
        </section>
        <section className="card chart-panel">
          <div className="panel-head">
            <h3>Bulk deals — est. return</h3>
            <Link to="/bulk" className="link-sm">See all →</Link>
          </div>
          {loading ? <p>Loading…</p> : <ReturnBarChart data={bulkChart} height={260} color="#22d3ee" />}
        </section>
      </div>

      <section className="card chart-panel">
        <div className="panel-head">
          <h3>Sector theme heat</h3>
          <Link to="/themes" className="link-sm">Explore themes →</Link>
        </div>
        {loading ? <p>Loading…</p> : <HeatBarChart data={heatData} height={240} />}
      </section>

      <div className="grid-2">
        <section className="card">
          <h3>Top demand picks <span className="badge badge-purple">no bulk</span></h3>
          {demandPicks.length === 0 ? (
            <p className="muted">No demand picks yet — check Theme Explorer or wait for refresh.</p>
          ) : (
            <div className="mini-list">
              {demandPicks.slice(0, 5).map((p, i) => (
                <div key={p.ticker} className="mini-row">
                  <span className="mini-rank">{i + 1}</span>
                  <div className="mini-body">
                    {p.signal_id ? (
                      <Link to={`/signals/${p.signal_id}`}><strong>{p.ticker}</strong></Link>
                    ) : (
                      <strong>{p.ticker}</strong>
                    )}
                    <span className="muted">{p.theme_name}</span>
                  </div>
                  <span className="ok">{fmtExp(p.expected_return_pct)}</span>
                  <span className={tierClass(p.tier)}>{p.tier}</span>
                </div>
              ))}
            </div>
          )}
        </section>
        <section className="card">
          <h3>Top bulk picks <span className="badge badge-blue">NSE</span></h3>
          {bulkPicks.length === 0 ? (
            <p className="muted">No bulk picks today yet.</p>
          ) : (
            <div className="mini-list">
              {bulkPicks.map((s, i) => (
                <div key={s.id} className="mini-row">
                  <span className="mini-rank">{i + 1}</span>
                  <div className="mini-body">
                    <Link to={`/signals/${s.id}`}><strong>{s.ticker}</strong></Link>
                    <span className="muted">{s.entity}</span>
                  </div>
                  <span className="ok">{fmtExp(s.return_distribution?.expected_return_pct as number)}</span>
                  <span>{fmtPct(s.calibrated_probability)}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
