import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import ExpandableStockPanel from "../components/ExpandableStockPanel";
import CompareTray, { CompareItem } from "../components/CompareTray";
import StickyHoldBar from "../components/StickyHoldBar";
import { usePriceCharts } from "../hooks/usePriceCharts";
import { useHoldPrefs } from "../hooks/useHoldPrefs";
import { apiFetch, LiveThemePick, SignalItem, ThemeSummary } from "../api";
import { fmtPct, fmtValue, fmtDateLabel } from "../utils/format";
import {
  bulkHoldMetrics,
  bulkProfitMetrics,
  demandHoldMetrics,
  demandProfitMetrics,
  pickRationale,
  PickView,
  signalRationale,
  signalTf,
} from "../utils/metrics";
import { TimeframeInfo, tfFromDist } from "../utils/timeframe";

type Tab = "demand" | "bulk" | "all";
type ExitFilter = "" | "week" | "long";

function pickTf(p: LiveThemePick): TimeframeInfo {
  return {
    hold_days: p.hold_days,
    hold_label_long: p.hold_label_long,
    hold_label_short: p.hold_label_short,
    entry_date: p.entry_date,
    entry_date_label: p.entry_date_label,
    entry_date_full: p.entry_date_full,
    exit_date_label: p.exit_date_label,
    exit_date_full: p.exit_date_full,
    exit_window_label: p.exit_window_label,
    review_date_label: p.review_date_label,
    countdown_label: p.countdown_label,
    hold_status: p.hold_status,
    timeframe_tier: p.timeframe_tier,
    days_remaining: p.days_remaining,
  };
}

export default function HomePage({ defaultTab = "demand" }: { defaultTab?: Tab }) {
  const [tab, setTab] = useState<Tab>(defaultTab);
  const [pickView, setPickView] = useState<PickView>("hold");
  const [exitFilter, setExitFilter] = useState<ExitFilter>("");
  const [sortExit, setSortExit] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const holdMode = useHoldPrefs();

  const [demand, setDemand] = useState<LiveThemePick[]>([]);
  const [bulkTop, setBulkTop] = useState<SignalItem[]>([]);
  const [bulkScoringNote, setBulkScoringNote] = useState("");
  const [allSignals, setAllSignals] = useState<SignalItem[]>([]);
  const [themes, setThemes] = useState<ThemeSummary[]>([]);
  const [market, setMarket] = useState("");
  const [themeFilter, setThemeFilter] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<{ themes: ThemeSummary[] }>("/themes")
      .then((d) => setThemes(d.themes))
      .catch(console.error);
  }, []);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const m = market ? `&market=${market}` : "";
        const [d, b, all] = await Promise.all([
          apiFetch<{ items: LiveThemePick[] }>(`/themes/live-picks?limit=30${m}`),
          apiFetch<{ items: SignalItem[]; scoring_note?: string }>(`/signals/top-picks?market=${market || "IN"}&limit=20&days=14`),
          apiFetch<{ items: SignalItem[] }>(`/signals?limit=80${market ? `&market=${market}` : ""}`),
        ]);
        setDemand(d.items);
        setBulkTop(b.items);
        setBulkScoringNote(b.scoring_note || "");
        setAllSignals(all.items);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [market]);

  function passesExitFilter(tf: TimeframeInfo) {
    if (!exitFilter) return true;
    const rem = tf.days_remaining;
    if (rem == null) return true;
    if (exitFilter === "week") return rem <= 7;
    if (exitFilter === "long") return (tf.hold_days || 0) >= 60;
    return true;
  }

  function sortByExit<T extends { tf: TimeframeInfo }>(rows: T[]) {
    if (!sortExit) return rows;
    return [...rows].sort((a, b) => (a.tf.days_remaining ?? 999) - (b.tf.days_remaining ?? 999));
  }

  const demandRows = useMemo(() => {
    let rows = demand.map((p) => ({ p, tf: pickTf(p) }));
    if (themeFilter) {
      rows = rows.filter((r) => r.p.theme_slug === themeFilter);
    }
    rows = rows.filter((r) => passesExitFilter(r.tf));
    rows.sort((a, b) => {
      const ab = a.p.investor_backing?.investors?.length ? 1 : 0;
      const bb = b.p.investor_backing?.investors?.length ? 1 : 0;
      if (ab !== bb) return bb - ab;
      return (b.p.composite_score ?? 0) - (a.p.composite_score ?? 0);
    });
    return sortByExit(rows);
  }, [demand, exitFilter, sortExit, themeFilter]);

  const allSignalsSorted = useMemo(() => {
    return [...allSignals].sort((a, b) => {
      const ab = a.investor_backing?.investors?.length ? 1 : 0;
      const bb = b.investor_backing?.investors?.length ? 1 : 0;
      if (ab !== bb) return bb - ab;
      return new Date(b.disclosed_at).getTime() - new Date(a.disclosed_at).getTime();
    });
  }, [allSignals]);

  const bulkRows = useMemo(() => {
    const rows = bulkTop.map((s) => ({ s, tf: tfFromDist(s.return_distribution) }))
      .filter((r) => passesExitFilter(r.tf));
    return sortByExit(rows);
  }, [bulkTop, exitFilter, sortExit]);

  const chartRequests = useMemo(() => {
    if (tab === "demand") return demand.map((p) => ({ ticker: p.ticker, market: p.market }));
    if (tab === "bulk") return bulkTop.map((s) => ({ ticker: s.ticker, market: s.market }));
    return allSignals.slice(0, 20).map((s) => ({ ticker: s.ticker, market: s.market }));
  }, [tab, demand, bulkTop, allSignals]);

  const { get, loading: chartsLoading } = usePriceCharts(chartRequests);

  useEffect(() => {
    setTab(defaultTab);
  }, [defaultTab]);

  function onCompareToggle(id: string, selected: boolean) {
    setCompareIds((prev) => {
      if (selected) {
        if (prev.includes(id)) return prev;
        if (prev.length >= 3) return prev;
        return [...prev, id];
      }
      return prev.filter((x) => x !== id);
    });
  }

  const compareItems: CompareItem[] = useMemo(() => {
    return compareIds.map((id) => {
      const bulk = bulkTop.find((s) => s.id === id);
      if (bulk) {
        const c = get(bulk.ticker, bulk.market);
        return {
          id,
          ticker: bulk.ticker,
          market: bulk.market,
          tier: bulk.tier,
          expected: bulk.return_distribution?.expected_return_pct as number | undefined,
          prob: bulk.calibrated_probability,
          tf: tfFromDist(bulk.return_distribution),
          prices: c?.prices,
          trend: c?.trend,
        };
      }
      const pick = demand.find((p) => p.signal_id === id);
      if (pick) {
        const c = get(pick.ticker, pick.market);
        return {
          id,
          ticker: pick.ticker,
          market: pick.market,
          tier: pick.tier,
          expected: pick.expected_return_pct,
          prob: pick.calibrated_probability,
          tf: pickTf(pick),
          prices: c?.prices,
          trend: c?.trend,
        };
      }
      return { id, ticker: "?", market: "?" };
    });
  }, [compareIds, bulkTop, demand, get]);

  const stickyTf = useMemo(() => {
    const rows = tab === "demand" ? demandRows : tab === "bulk" ? bulkRows : [];
    const urgent = rows.find((r) => (r.tf.days_remaining ?? 999) <= 7);
    return urgent?.tf;
  }, [tab, demandRows, bulkRows]);

  return (
    <div className="home-page">
      {pickView === "hold" && stickyTf && (
        <StickyHoldBar tf={stickyTf} label={tab === "bulk" ? "Next bulk exit" : "Next demand exit"} />
      )}

      <div className="page-intro">
        <h2>Trade Bot</h2>
        <p className="muted">
          {pickView === "hold"
            ? "Hold plan — when to review and sell. No profit targets here."
            : "Profit outlook — estimated returns with P/E, margins, and rationale."}
        </p>
      </div>

      <section className="home-controls">
        <div className="control-row control-row-primary">
          <div className="source-tabs">
            <button type="button" className={tab === "demand" ? "active" : ""} onClick={() => setTab("demand")}>
              Demand <span className="count">{demand.length}</span>
            </button>
            <button type="button" className={tab === "bulk" ? "active" : ""} onClick={() => setTab("bulk")}>
              Bulk <span className="count">{bulkTop.length}</span>
            </button>
            <button type="button" className={tab === "all" ? "active" : ""} onClick={() => setTab("all")}>
              All signals
            </button>
          </div>
          {(tab === "demand" || tab === "bulk") && (
            <div className="segmented" role="group" aria-label="Hold or profit view">
              <button type="button" className={pickView === "hold" ? "active" : ""} onClick={() => setPickView("hold")}>
                Hold plan
              </button>
              <button type="button" className={pickView === "profit" ? "active" : ""} onClick={() => setPickView("profit")}>
                Profit outlook
              </button>
            </div>
          )}
        </div>

        <div className="control-row">
          <label className="filter-field">
            Market
            <select value={market} onChange={(e) => setMarket(e.target.value)}>
              <option value="">All</option>
              <option value="IN">India</option>
              <option value="US">US</option>
            </select>
          </label>

          {tab === "demand" && (
            <label className="filter-field">
              Theme
              <select
                value={themeFilter}
                onChange={(e) => setThemeFilter(e.target.value)}
              >
                <option value="">All themes</option>
                {themes.map((t) => (
                  <option key={t.slug} value={t.slug}>
                    {t.name.split("&")[0].trim()} ({Math.round((t.theme_heat || 0) * 100)}%)
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="filter-field">
            Exit
            <select value={exitFilter} onChange={(e) => setExitFilter(e.target.value as ExitFilter)}>
              <option value="">Any time</option>
              <option value="week">This week</option>
              <option value="long">60+ days</option>
            </select>
          </label>

          <label className="filter-check">
            <input type="checkbox" checked={sortExit} onChange={(e) => setSortExit(e.target.checked)} />
            Sort by exit
          </label>
          <label className="filter-check">
            <input type="checkbox" checked={compareMode} onChange={(e) => setCompareMode(e.target.checked)} />
            Compare
          </label>

          {tab === "demand" && (
            <Link to="/themes" className="themes-link">Browse all themes →</Link>
          )}
        </div>
      </section>

      {tab === "demand" && !loading && market === "IN" && !themeFilter && (
        <p className="muted market-hint">
          US names (MU, WDC, AMD) are demand picks — switch <strong>Market → US</strong> or pick a theme above.
        </p>
      )}

      {tab === "bulk" && !loading && bulkScoringNote && (
        <p className="muted market-hint scoring-hint">{bulkScoringNote}</p>
      )}

      {tab === "bulk" && !loading && (
        <p className="muted market-hint">
          Bulk deals are NSE India only. US stocks appear under <strong>Demand</strong>.
        </p>
      )}

      {loading && <p className="muted">Loading…</p>}

      {!loading && tab === "demand" && (
        <div className="panel-list">
          {demandRows.length === 0 ? (
            <p className="muted">No demand picks match filters.</p>
          ) : (
            demandRows.map(({ p, tf }, i) => {
              const c = get(p.ticker, p.market);
              const metrics = pickView === "hold" ? demandHoldMetrics(p, tf, holdMode) : demandProfitMetrics(p, tf);
              return (
                <ExpandableStockPanel
                  key={`${p.theme_slug}-${p.ticker}`}
                  rank={i + 1}
                  ticker={p.ticker}
                  market={p.market}
                  signalId={p.signal_id}
                  headline={`${p.company_name} · ${p.theme_name}`}
                  subline={
                    pickView === "profit"
                      ? pickRationale(p)
                      : p.investor_backing
                        ? [
                            `${fmtValue(p.investor_backing.total_value, p.market)} backed · ${p.investor_backing.investor_count} investors`,
                            p.demand_driver,
                          ].filter(Boolean).join(" · ")
                        : p.demand_driver
                  }
                  tier={p.tier}
                  timeframe={tf}
                  showTimeline={pickView === "hold"}
                  compareMode={compareMode}
                  compareSelected={p.signal_id ? compareIds.includes(p.signal_id) : false}
                  onCompareToggle={onCompareToggle}
                  metrics={metrics}
                  tags={[
                    pickView === "hold" ? "Hold plan" : "Profit outlook",
                    p.market,
                    p.bulk_backed ? "Bulk backed" : "Demand pick",
                    p.bulk_confirmed ? "Bulk confirmed" : p.has_bulk_deal ? "Also has bulk" : null,
                    tf.timeframe_tier || "",
                  ].filter(Boolean) as string[]}
                  prices={c?.prices}
                  trend={c?.trend}
                  chartLoading={chartsLoading && !c}
                  investorBacking={p.investor_backing}
                  prediction={p.prediction}
                />
              );
            })
          )}
        </div>
      )}

      {!loading && tab === "bulk" && (
        <div className="panel-list">
          {bulkRows.length === 0 ? (
            <p className="muted">No NSE bulk/block deals in the last 14 days{market ? ` for ${market}` : ""}. Check back after the 18:15 IST ingest.</p>
          ) : (
            bulkRows.map(({ s, tf }, i) => {
              const c = get(s.ticker, s.market);
              const metrics = pickView === "hold" ? bulkHoldMetrics(s, tf, holdMode) : bulkProfitMetrics(s, tf);
              return (
                <ExpandableStockPanel
                  key={s.id}
                  rank={i + 1}
                  ticker={s.ticker}
                  market={s.market}
                  signalId={s.id}
                  headline={`${s.ticker} · ${s.action} · ${s.entity}`}
                  subline={pickView === "profit" ? signalRationale(s) : [
                    s.investor_backing
                      ? `${fmtValue(s.investor_backing.total_value, s.market)} backed · ${s.investor_backing.investor_count} investors`
                      : fmtValue(s.value, s.market),
                    tf.entry_date_label || fmtDateLabel(s.disclosed_at, true),
                    fmtPct(s.calibrated_probability, 1) + " conf",
                    s.bulk_deal_count_week && s.bulk_deal_count_week > 1
                      ? `${s.bulk_deal_count_week} bulk deals this week`
                      : null,
                  ].filter(Boolean).join(" · ")}
                  tier={s.tier}
                  timeframe={tf}
                  showTimeline={pickView === "hold"}
                  compareMode={compareMode}
                  compareSelected={compareIds.includes(s.id)}
                  onCompareToggle={onCompareToggle}
                  metrics={metrics}
                  investorBacking={s.investor_backing}
                  prediction={s.prediction}
                  tags={[
                    pickView === "hold" ? "Hold plan" : "Profit outlook",
                    "NSE bulk/block",
                    s.source.replace("nse_", ""),
                    tf.timeframe_tier || "",
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

      {!loading && tab === "all" && (
        <div className="panel-list">
          {allSignalsSorted.map((s, i) => {
            const c = get(s.ticker, s.market);
            const isMacro = s.source === "macro_theme";
            const tf = signalTf(s);
            const metrics = isMacro
              ? (pickView === "hold" ? demandHoldMetrics({
                  tier: s.tier,
                  theme_heat: s.theme?.theme_heat,
                  expected_return_pct: s.return_distribution?.expected_return_pct as number,
                  calibrated_probability: s.calibrated_probability,
                } as LiveThemePick, tf, holdMode) : demandProfitMetrics({
                  tier: s.tier,
                  expected_return_pct: s.return_distribution?.expected_return_pct as number,
                  calibrated_probability: s.calibrated_probability,
                  fundamentals: s.return_distribution?.fundamentals as LiveThemePick["fundamentals"],
                  return_rationale: s.return_distribution?.return_rationale as string,
                } as LiveThemePick, tf))
              : (pickView === "hold" ? bulkHoldMetrics(s, tf, holdMode) : bulkProfitMetrics(s, tf));
            const bulkSubline = s.investor_backing
              ? [
                  `${fmtValue(s.investor_backing.total_value, s.market)} backed · ${s.investor_backing.investor_count} investors`,
                  tf.entry_date_label || fmtDateLabel(s.disclosed_at, true),
                  fmtPct(s.calibrated_probability, 1) + " conf",
                ].filter(Boolean).join(" · ")
              : `${s.action} · ${s.source} · ${fmtDateLabel(s.disclosed_at, true)}`;
            return (
              <ExpandableStockPanel
                key={s.id}
                rank={i + 1}
                ticker={s.ticker}
                market={s.market}
                signalId={s.id}
                headline={isMacro ? `${s.ticker} · ${s.theme?.name || s.entity}` : `${s.ticker} · ${s.entity}`}
                subline={isMacro ? `${s.action} · ${s.source} · ${fmtDateLabel(s.disclosed_at, true)}` : bulkSubline}
                tier={s.tier}
                timeframe={tf}
                showTimeline={pickView === "hold"}
                metrics={metrics}
                investorBacking={s.investor_backing}
                prediction={s.prediction}
                tags={[isMacro ? "Demand" : "Bulk", s.market, s.investor_backing ? "Smart-money" : "", pickView === "hold" ? "Hold" : "Profit"].filter(Boolean)}
                prices={c?.prices}
                trend={c?.trend}
                chartLoading={chartsLoading && !c}
              />
            );
          })}
        </div>
      )}

      <CompareTray items={compareItems} onClear={() => setCompareIds([])} />
    </div>
  );
}
