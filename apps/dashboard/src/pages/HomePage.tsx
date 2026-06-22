import { useEffect, useMemo, useState } from "react";
import StockPanel, { bulkMetrics } from "../components/StockPanel";
import { usePriceCharts } from "../hooks/usePriceCharts";
import { apiFetch, LiveThemePick, SignalItem } from "../api";
import { fmtExp, fmtPct } from "../utils/format";

type Tab = "demand" | "bulk" | "all";

export default function HomePage({ defaultTab = "demand" }: { defaultTab?: Tab }) {
  const [tab, setTab] = useState<Tab>(defaultTab);

  const [demand, setDemand] = useState<LiveThemePick[]>([]);
  const [bulkTop, setBulkTop] = useState<SignalItem[]>([]);
  const [allSignals, setAllSignals] = useState<SignalItem[]>([]);
  const [market, setMarket] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const m = market ? `&market=${market}` : "";
      const [d, b, all] = await Promise.all([
        apiFetch<{ items: LiveThemePick[] }>(`/themes/live-picks?limit=20&no_bulk_only=true${m}`),
        apiFetch<{ items: SignalItem[] }>(`/signals/top-picks?market=${market || "IN"}&limit=10`),
        apiFetch<{ items: SignalItem[] }>(`/signals?limit=40${market ? `&market=${market}` : ""}`),
      ]);
      setDemand(d.items);
      setBulkTop(b.items);
      setAllSignals(all.items);
      setLoading(false);
    }
    load().catch(console.error);
  }, [market]);

  const chartRequests = useMemo(() => {
    if (tab === "demand") return demand.map((p) => ({ ticker: p.ticker, market: p.market }));
    if (tab === "bulk") return bulkTop.map((s) => ({ ticker: s.ticker, market: s.market }));
    return allSignals.slice(0, 20).map((s) => ({ ticker: s.ticker, market: s.market }));
  }, [tab, demand, bulkTop, allSignals]);

  const { get, loading: chartsLoading } = usePriceCharts(chartRequests);

  useEffect(() => {
    setTab(defaultTab);
  }, [defaultTab]);

  return (
    <div>
      <div className="page-intro">
        <h2>Smart-Money Tracker</h2>
        <p className="muted">Each row shows a live 6-month price chart plus scores. Demand tab = predicted from world trends, no bulk deal needed.</p>
      </div>

      <div className="tabs">
        <button type="button" className={tab === "demand" ? "active" : ""} onClick={() => setTab("demand")}>
          Demand picks <span className="count">{demand.length}</span>
        </button>
        <button type="button" className={tab === "bulk" ? "active" : ""} onClick={() => setTab("bulk")}>
          Bulk deals <span className="count">{bulkTop.length}</span>
        </button>
        <button type="button" className={tab === "all" ? "active" : ""} onClick={() => setTab("all")}>
          All signals
        </button>
        <select className="tab-select" value={market} onChange={(e) => setMarket(e.target.value)}>
          <option value="">All markets</option>
          <option value="IN">India</option>
          <option value="US">US</option>
        </select>
      </div>

      {loading && <p className="muted">Loading…</p>}

      {!loading && tab === "demand" && (
        <div className="panel-list">
          {demand.length === 0 ? (
            <p className="muted">No demand picks — theme refresh runs at 6:45 PM IST.</p>
          ) : (
            demand.map((p, i) => {
              const c = get(p.ticker, p.market);
              return (
                <StockPanel
                  key={`${p.theme_slug}-${p.ticker}`}
                  rank={i + 1}
                  ticker={p.ticker}
                  market={p.market}
                  signalId={p.signal_id}
                  headline={`${p.company_name} · ${p.theme_name}`}
                  subline={p.demand_driver}
                  tier={p.tier}
                  note={p.sell_horizon_label}
                  metrics={[
                    { label: "Est. return", value: fmtExp(p.expected_return_pct), accent: true },
                    { label: "Confidence", value: fmtPct(p.calibrated_probability) },
                    { label: "Theme heat", value: fmtPct(p.theme_heat) },
                    { label: "Alignment", value: fmtPct(p.alignment_score) },
                    { label: "1mo", value: fmtPct(c?.trend?.return_1m, 1) },
                    { label: "3mo", value: fmtPct(c?.trend?.return_3m, 1) },
                  ]}
                  tags={[
                    "Demand pick",
                    p.has_bulk_deal ? "Also has bulk" : "No bulk deal",
                    c?.trend?.momentum || "",
                  ].filter(Boolean)}
                  prices={c?.prices}
                  trend={c?.trend}
                  chartLoading={chartsLoading && !c}
                />
              );
            })
          )}
        </div>
      )}

      {!loading && tab === "bulk" && (
        <div className="panel-list">
          {bulkTop.length === 0 ? (
            <p className="muted">No bulk picks today yet.</p>
          ) : (
            bulkTop.map((s, i) => {
              const c = get(s.ticker, s.market);
              return (
                <StockPanel
                  key={s.id}
                  rank={i + 1}
                  ticker={s.ticker}
                  market={s.market}
                  signalId={s.id}
                  headline={`${s.ticker} · ${s.action} · ${s.entity}`}
                  subline={`Deal ${fmtPct(s.calibrated_probability)} confidence · ${new Date(s.disclosed_at).toLocaleDateString()}`}
                  tier={s.tier}
                  metrics={bulkMetrics(s)}
                  tags={["NSE bulk/block", s.source.replace("nse_", "")]}
                  prices={c?.prices}
                  trend={c?.trend}
                  chartLoading={chartsLoading && !c}
                />
              );
            })
          )}
        </div>
      )}

      {!loading && tab === "all" && (
        <div className="panel-list">
          {allSignals.map((s, i) => {
            const c = get(s.ticker, s.market);
            const isMacro = s.source === "macro_theme";
            return (
              <StockPanel
                key={s.id}
                rank={i + 1}
                ticker={s.ticker}
                market={s.market}
                signalId={s.id}
                headline={isMacro ? `${s.ticker} · ${s.theme?.name || s.entity}` : `${s.ticker} · ${s.entity}`}
                subline={`${s.action} · ${s.source} · ${new Date(s.disclosed_at).toLocaleDateString()}`}
                tier={s.tier}
                metrics={isMacro ? [
                  { label: "Est. return", value: fmtExp(s.return_distribution?.expected_return_pct as number), accent: true },
                  { label: "Confidence", value: fmtPct(s.calibrated_probability) },
                  { label: "Theme heat", value: fmtPct(s.theme?.theme_heat) },
                ] : bulkMetrics(s)}
                tags={[isMacro ? "Demand" : "Bulk", s.market]}
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
