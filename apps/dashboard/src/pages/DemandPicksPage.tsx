import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { HeatBarChart, ReturnBarChart } from "../components/Charts";
import StatCard from "../components/StatCard";
import { apiFetch, LiveThemePick, ThemeSummary } from "../api";
import { fmtExp, fmtPct, tierClass } from "../utils/format";

export default function DemandPicksPage() {
  const [picks, setPicks] = useState<LiveThemePick[]>([]);
  const [themes, setThemes] = useState<ThemeSummary[]>([]);
  const [market, setMarket] = useState("");
  const [themeFilter, setThemeFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const params = new URLSearchParams({ limit: "30", no_bulk_only: "true" });
      if (market) params.set("market", market);
      const [live, themeData] = await Promise.all([
        apiFetch<{ items: LiveThemePick[] }>(`/themes/live-picks?${params}`),
        apiFetch<{ themes: ThemeSummary[] }>(`/themes${market ? `?market=${market}` : ""}`),
      ]);
      setPicks(live.items);
      setThemes(themeData.themes);
      setLoading(false);
    }
    load().catch(console.error);
  }, [market]);

  const filtered = useMemo(() => {
    if (!themeFilter) return picks;
    return picks.filter((p) => p.theme_slug === themeFilter);
  }, [picks, themeFilter]);

  const chartData = filtered.slice(0, 10).map((p) => ({
    name: p.ticker,
    value: (p.expected_return_pct || 0) * 100,
  }));

  const heatData = themes.map((t) => ({
    name: t.name.replace(/ &.*/, "").slice(0, 18),
    heat: Math.round((t.theme_heat || 0) * 100),
  }));

  const noBulkCount = picks.filter((p) => !p.has_bulk_deal).length;

  return (
    <div className="page-stack">
      <section className="hero-banner demand-hero">
        <div>
          <span className="eyebrow">No bulk deal required</span>
          <h2>Demand & macro predictions</h2>
          <p>
            Stocks predicted to rise from world affairs and sector demand — AI storage (SanDisk/WDC),
            semis, defense, power, minerals — scored vs live sector proxies.
          </p>
        </div>
        <div className="hero-stats">
          <StatCard label="Live picks" value={String(picks.length)} sub="updated now" accent="purple" />
          <StatCard label="No bulk deal" value={String(noBulkCount)} sub="theme-only" accent="green" />
          <StatCard label="Themes" value={String(themes.length)} sub="active sectors" accent="blue" />
        </div>
      </section>

      <div className="toolbar toolbar-card">
        <select value={market} onChange={(e) => setMarket(e.target.value)}>
          <option value="">All markets</option>
          <option value="IN">India</option>
          <option value="US">United States</option>
        </select>
        <select value={themeFilter} onChange={(e) => setThemeFilter(e.target.value)}>
          <option value="">All themes</option>
          {themes.map((t) => (
            <option key={t.slug} value={t.slug}>{t.name}</option>
          ))}
        </select>
      </div>

      <div className="grid-2">
        <section className="card chart-panel">
          <h3>Est. return — top demand picks</h3>
          <p className="muted">Stocks without recent bulk buying highlighted below</p>
          {loading ? <p>Loading chart…</p> : <ReturnBarChart data={chartData} height={300} />}
        </section>
        <section className="card chart-panel">
          <h3>Theme heat (sector momentum)</h3>
          <p className="muted">How hot each demand theme is right now</p>
          {loading ? <p>Loading…</p> : <HeatBarChart data={heatData} height={300} />}
        </section>
      </div>

      {loading ? (
        <p className="loading-msg">Loading demand picks…</p>
      ) : filtered.length === 0 ? (
        <section className="card empty-state">
          <h3>No picks match filters</h3>
          <p className="muted">Try clearing market/theme filters or check back after the 6:45 PM theme refresh.</p>
        </section>
      ) : (
        <div className="pick-grid">
          {filtered.map((p, i) => (
            <article key={`${p.theme_slug}-${p.ticker}`} className="pick-card">
              <div className="pick-card-head">
                <div>
                  <span className="pick-rank">#{i + 1}</span>
                  <h3>
                    {p.signal_id ? (
                      <Link to={`/signals/${p.signal_id}`}>{p.ticker}</Link>
                    ) : (
                      p.ticker
                    )}
                  </h3>
                  <p className="pick-company">{p.company_name}</p>
                </div>
                <span className={tierClass(p.tier)}>{p.tier}</span>
              </div>
              <p className="pick-theme">{p.theme_name}</p>
              <div className="pick-metrics">
                <div><span>Est. return</span><strong className="ok">{fmtExp(p.expected_return_pct)}</strong></div>
                <div><span>Confidence</span><strong>{fmtPct(p.calibrated_probability)}</strong></div>
                <div><span>Theme heat</span><strong>{fmtPct(p.theme_heat)}</strong></div>
                <div><span>Alignment</span><strong>{fmtPct(p.alignment_score)}</strong></div>
              </div>
              <div className="pick-tags">
                <span className="tag">{p.market}</span>
                {!p.has_bulk_deal && <span className="tag tag-green">No bulk deal</span>}
                {p.has_bulk_deal && <span className="tag tag-amber">Also has bulk activity</span>}
              </div>
              {p.signal_id && (
                <Link to={`/signals/${p.signal_id}`} className="pick-link">View full thesis & chart →</Link>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
