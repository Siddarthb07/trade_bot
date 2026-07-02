import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import ExpandableStockPanel from "../components/ExpandableStockPanel";
import StatCard from "../components/StatCard";
import { usePriceCharts } from "../hooks/usePriceCharts";
import { apiFetch, LiveThemePick, SignalItem } from "../api";
import { fmtExp, fmtPct, fmtValue, tierClass } from "../utils/format";
import { tfFromDist } from "../utils/timeframe";

export default function DemandPicksPage() {
  const [picks, setPicks] = useState<LiveThemePick[]>([]);
  const [market, setMarket] = useState("");
  const [themeFilter, setThemeFilter] = useState("");
  const [showBulkConfirmed, setShowBulkConfirmed] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const params = new URLSearchParams({ limit: "30" });
        if (!showBulkConfirmed) params.set("no_bulk_only", "true");
        if (market) params.set("market", market);
        const live = await apiFetch<{ items: LiveThemePick[] }>(`/themes/live-picks?${params}`);
        setPicks(live.items);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [market, showBulkConfirmed]);

  const filtered = useMemo(() => {
    if (!themeFilter) return picks;
    return picks.filter((p) => p.theme_slug === themeFilter);
  }, [picks, themeFilter]);

  const themes = useMemo(() => {
    const seen = new Map<string, string>();
    picks.forEach((p) => seen.set(p.theme_slug, p.theme_name));
    return [...seen.entries()].map(([slug, name]) => ({ slug, name }));
  }, [picks]);

  const chartReq = useMemo(
    () => filtered.map((p) => ({ ticker: p.ticker, market: p.market })),
    [filtered],
  );
  const { get, loading: chartsLoading } = usePriceCharts(chartReq);

  const noBulkCount = picks.filter((p) => !p.has_bulk_deal).length;

  return (
    <div className="page-stack">
      <section className="hero-banner demand-hero">
        <div>
          <span className="eyebrow">No bulk deal required</span>
          <h2>Demand & macro predictions</h2>
          <p>Per-stock charts with hold/sell-by dates. Expand any row for inline thesis.</p>
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
        <label className="tab-check">
          <input type="checkbox" checked={showBulkConfirmed} onChange={(e) => setShowBulkConfirmed(e.target.checked)} />
          Include bulk-confirmed
        </label>
      </div>

      {loading ? (
        <p className="loading-msg">Loading demand picks…</p>
      ) : filtered.length === 0 ? (
        <section className="card empty-state">
          <h3>No picks match filters</h3>
        </section>
      ) : (
        <div className="panel-list">
          {filtered.map((p, i) => {
            const c = get(p.ticker, p.market);
            const tf = {
              hold_days: p.hold_days,
              hold_label_long: p.hold_label_long,
              exit_date_label: p.exit_date_label,
              exit_date_full: p.exit_date_full,
              review_date_label: p.review_date_label,
              countdown_label: p.countdown_label,
              hold_status: p.hold_status,
              timeframe_tier: p.timeframe_tier,
              days_remaining: p.days_remaining,
            };
            return (
              <ExpandableStockPanel
                key={`${p.theme_slug}-${p.ticker}`}
                rank={i + 1}
                ticker={p.ticker}
                market={p.market}
                signalId={p.signal_id}
                headline={`${p.company_name} · ${p.theme_name}`}
                subline={p.demand_driver}
                tier={p.tier}
                timeframe={tf}
                metrics={[
                  { label: "Est. return", value: fmtExp(p.expected_return_pct), accent: true },
                  { label: "Confidence", value: fmtPct(p.calibrated_probability) },
                  { label: "Sell by", value: tf.exit_date_label || "—" },
                  { label: "Theme heat", value: fmtPct(p.theme_heat) },
                ]}
                tags={[
                  p.market,
                  !p.has_bulk_deal ? "No bulk deal" : "",
                  p.bulk_confirmed ? "Bulk confirmed" : "",
                ].filter(Boolean)}
                prices={c?.prices}
                trend={c?.trend}
                chartLoading={chartsLoading && !c}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
