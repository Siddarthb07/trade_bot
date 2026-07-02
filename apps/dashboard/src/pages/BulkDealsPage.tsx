import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import ExpandableStockPanel from "../components/ExpandableStockPanel";
import StatCard from "../components/StatCard";
import { bulkMetrics } from "../components/StockPanel";
import { usePriceCharts } from "../hooks/usePriceCharts";
import { apiFetch, SignalItem } from "../api";
import { fmtExp, fmtPct, fmtValue, tierClass } from "../utils/format";
import { tfFromDist } from "../utils/timeframe";

export default function BulkDealsPage() {
  const [items, setItems] = useState<SignalItem[]>([]);
  const [topPicks, setTopPicks] = useState<SignalItem[]>([]);
  const [scoringNote, setScoringNote] = useState("");
  const [market, setMarket] = useState("IN");
  const [tier, setTier] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
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
          apiFetch<{ items: SignalItem[]; scoring_note?: string }>(`/signals/top-picks?market=${market || "IN"}&limit=8&days=14`).catch(() => ({ items: [] })),
        ]);
        const merged = [...bulk.items, ...block.items].sort(
          (a, b) => new Date(b.disclosed_at).getTime() - new Date(a.disclosed_at).getTime(),
        );
        setItems(merged);
        setTopPicks(picks.items);
        setScoringNote(picks.scoring_note || "");
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [market, tier]);

  const chartReq = useMemo(
    () => topPicks.map((s) => ({ ticker: s.ticker, market: s.market })),
    [topPicks],
  );
  const { get, loading: chartsLoading } = usePriceCharts(chartReq);

  return (
    <div className="page-stack">
      <section className="hero-banner bulk-hero">
        <div>
          <span className="eyebrow">NSE bulk & block deals</span>
          <h2>Smart-money bulk deals</h2>
          <p>One row per ticker — expand for thesis and investor table.</p>
        </div>
        <div className="hero-stats">
          <StatCard label="Recent deals" value={String(items.length)} accent="blue" />
          <StatCard label="Top picks" value={String(topPicks.length)} sub="deduped" accent="amber" />
        </div>
      </section>

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

      {scoringNote && <p className="muted market-hint scoring-hint">{scoringNote}</p>}

      {loading && <p className="muted">Loading…</p>}

      {!loading && topPicks.length > 0 && (
        <section className="card">
          <h3>Today&apos;s top bulk picks (deduped)</h3>
          <div className="panel-list panel-list-nested">
            {topPicks.map((s, i) => {
              const c = get(s.ticker, s.market);
              const tf = tfFromDist(s.return_distribution);
              return (
                <ExpandableStockPanel
                  key={s.id}
                  rank={i + 1}
                  ticker={s.ticker}
                  market={s.market}
                  signalId={s.id}
                  headline={`${s.ticker} · ${s.entity}`}
                  subline={[
                    s.investor_backing
                      ? `${fmtValue(s.investor_backing.total_value, s.market)} · ${s.investor_backing.investor_count} investors`
                      : fmtValue(s.value, s.market),
                    fmtPct(s.calibrated_probability) + " conf",
                    s.bulk_deal_count_week && s.bulk_deal_count_week > 1
                      ? `${s.bulk_deal_count_week} bulk deals this week`
                      : null,
                  ].filter(Boolean).join(" · ")}
                  tier={s.tier}
                  timeframe={tf}
                  metrics={bulkMetrics(s)}
                  investorBacking={s.investor_backing}
                  prediction={s.prediction}
                  tags={["Top pick"]}
                  prices={c?.prices}
                  trend={c?.trend}
                  chartLoading={chartsLoading && !c}
                />
              );
            })}
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
