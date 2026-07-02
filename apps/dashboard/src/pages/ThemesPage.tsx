import { useEffect, useMemo, useState } from "react";
import ExpandableStockPanel from "../components/ExpandableStockPanel";
import { MiniPriceChart } from "../components/PriceChart";
import { usePriceCharts } from "../hooks/usePriceCharts";
import { apiFetch, LiveThemePick, ThemeSummary } from "../api";
import { fmtExp, fmtPct } from "../utils/format";

export default function ThemesPage() {
  const [themes, setThemes] = useState<ThemeSummary[]>([]);
  const [liveByTicker, setLiveByTicker] = useState<Record<string, LiveThemePick>>({});
  const [active, setActive] = useState("");
  const [market, setMarket] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const m = market ? `?market=${market}` : "";
        const liveParams = new URLSearchParams({ limit: "50" });
        if (market) liveParams.set("market", market);
        const [themeData, live] = await Promise.all([
          apiFetch<{ themes: ThemeSummary[] }>(`/themes${m}`),
          apiFetch<{ items: LiveThemePick[] }>(`/themes/live-picks?${liveParams}`),
        ]);
        setThemes(themeData.themes);
        const map: Record<string, LiveThemePick> = {};
        live.items.forEach((p) => { map[`${p.market}:${p.ticker}`] = p; });
        setLiveByTicker(map);
        setActive((prev) => prev || themeData.themes[0]?.slug || "");
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [market]);

  const current = themes.find((t) => t.slug === active) || themes[0];
  const picks = current?.top_picks || [];

  const chartReq = useMemo(() => picks.map((p) => ({ ticker: p.ticker, market: p.market })), [picks]);
  const { get, loading: chartsLoading } = usePriceCharts(chartReq);

  const proxyPrices = (current?.proxy_prices || []).map((p) => ({
    date: p.date,
    close: p.close,
    volume: p.volume,
  }));

  return (
    <div>
      <div className="page-intro">
        <h2>Theme explorer</h2>
        <p className="muted">Sector proxy chart + top stocks with hold/sell-by dates.</p>
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
          <div className="theme-detail-grid">
            <div>
              <h3>{current.name}</h3>
              <p className="why-now"><strong>Why now:</strong> {current.world_context}</p>
              <p className="muted">{current.demand_driver}</p>
              <p className="muted">Sector proxy: {current.proxy_ticker} · 3mo {fmtPct(current.proxy_return_3m, 1)}</p>
            </div>
            <div className="theme-proxy-chart">
              <h4>Proxy — {current.proxy_ticker}</h4>
              <MiniPriceChart prices={proxyPrices} height={120} />
            </div>
          </div>
        </section>
      )}

      <div className="panel-list">
        {picks.map((p, i) => {
          const c = get(p.ticker, p.market);
          const live = liveByTicker[`${p.market}:${p.ticker}`];
          const tf = live ? {
            hold_days: live.hold_days,
            hold_label_long: live.hold_label_long,
            hold_label_short: live.hold_label_short,
            exit_date_label: live.exit_date_label,
            exit_date_full: live.exit_date_full,
            review_date_label: live.review_date_label,
            countdown_label: live.countdown_label,
            hold_status: live.hold_status,
            timeframe_tier: live.timeframe_tier,
            days_remaining: live.days_remaining,
          } : undefined;
          return (
            <ExpandableStockPanel
              key={`${p.theme_slug}-${p.ticker}`}
              rank={i + 1}
              ticker={p.ticker}
              market={p.market}
              signalId={live?.signal_id}
              headline={p.company_name}
              subline={current?.demand_driver}
              tier={p.tier}
              timeframe={tf}
              metrics={[
                { label: "Est. return", value: fmtExp(p.expected_return_pct), accent: true },
                { label: "Confidence", value: fmtPct(p.calibrated_probability) },
                { label: "Sell by", value: tf?.exit_date_label || "—" },
                { label: "Review", value: tf?.review_date_label || "—" },
                { label: "Theme heat", value: fmtPct(p.theme_heat) },
                { label: "Left", value: tf?.countdown_label || "—" },
              ]}
              tags={[p.market, current?.name || "", tf?.timeframe_tier || ""].filter(Boolean)}
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
