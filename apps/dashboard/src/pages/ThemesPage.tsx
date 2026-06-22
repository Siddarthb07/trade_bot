import { useEffect, useMemo, useState } from "react";
import StockPanel from "../components/StockPanel";
import { usePriceCharts } from "../hooks/usePriceCharts";
import { apiFetch, ThemeSummary } from "../api";
import { fmtExp, fmtPct } from "../utils/format";

export default function ThemesPage() {
  const [themes, setThemes] = useState<ThemeSummary[]>([]);
  const [active, setActive] = useState("");
  const [market, setMarket] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<{ themes: ThemeSummary[] }>(`/themes${market ? `?market=${market}` : ""}`)
      .then((d) => {
        setThemes(d.themes);
        setActive((prev) => prev || d.themes[0]?.slug || "");
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [market]);

  const current = themes.find((t) => t.slug === active) || themes[0];
  const picks = current?.top_picks || [];

  const chartReq = useMemo(() => picks.map((p) => ({ ticker: p.ticker, market: p.market })), [picks]);
  const { get, loading: chartsLoading } = usePriceCharts(chartReq);

  return (
    <div>
      <div className="page-intro">
        <h2>Theme explorer</h2>
        <p className="muted">Pick a demand theme — each stock gets its own price chart and scores.</p>
      </div>

      <div className="tabs">
        {themes.map((t) => (
          <button
            key={t.slug}
            type="button"
            className={t.slug === active ? "active" : ""}
            onClick={() => setActive(t.slug)}
          >
            {t.name.split("&")[0].trim()}
            <span className="count">{Math.round((t.theme_heat || 0) * 100)}%</span>
          </button>
        ))}
        <select className="tab-select" value={market} onChange={(e) => setMarket(e.target.value)}>
          <option value="">All markets</option>
          <option value="IN">India</option>
          <option value="US">US</option>
        </select>
      </div>

      {loading && <p className="muted">Loading…</p>}

      {current && (
        <section className="card theme-detail">
          <h3>{current.name}</h3>
          <p>{current.world_context}</p>
          <p className="muted">{current.demand_driver}</p>
          <p className="muted">Sector proxy: {current.proxy_ticker} · 3mo {fmtPct(current.proxy_return_3m, 1)}</p>
        </section>
      )}

      <div className="panel-list">
        {picks.map((p, i) => {
          const c = get(p.ticker, p.market);
          return (
            <StockPanel
              key={`${p.theme_slug}-${p.ticker}`}
              rank={i + 1}
              ticker={p.ticker}
              market={p.market}
              headline={`${p.company_name}`}
              subline={current?.demand_driver}
              tier={p.tier}
              metrics={[
                { label: "Est. return", value: fmtExp(p.expected_return_pct), accent: true },
                { label: "Confidence", value: fmtPct(p.calibrated_probability) },
                { label: "Theme heat", value: fmtPct(p.theme_heat) },
                { label: "Alignment", value: fmtPct(p.alignment_score) },
                { label: "1mo", value: fmtPct(c?.trend?.return_1m, 1) },
                { label: "3mo", value: fmtPct(c?.trend?.return_3m, 1) },
              ]}
              tags={[p.market, current?.name || ""]}
              prices={c?.prices}
              trend={c?.trend}
              chartLoading={chartsLoading && !c}
            />
          );
        })}
      </div>
    </div>
  );
}
