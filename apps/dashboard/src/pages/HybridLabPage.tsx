import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api";
import HybridRunnerBar from "../components/hybrid/HybridRunnerBar";
import HybridSessionTape from "../components/hybrid/HybridSessionTape";
import StrategyDecisionCard from "../components/hybrid/StrategyDecisionCard";
import UniverseLadderList from "../components/hybrid/UniverseLadderList";
import HybridTradeCard, { type TradeRow } from "../components/hybrid/HybridTradeCard";
import StrategyRegistryPanel, { EquitySpark } from "../components/hybrid/StrategyRegistryPanel";
import {
  type BarInterval,
  type LabMode,
  type Lane,
  barsToPrices,
  clsPnL,
  fmtInr,
  fmtNum,
  fmtPct,
} from "../components/hybrid/format";
import { DetailPriceChart, type PricePoint, type TradeMarker } from "../components/PriceChart";

type BenchWindow = { id: string; label?: string };

export default function HybridLabPage() {
  const [lane, setLane] = useState<Lane>("product");
  const [windowId, setWindowId] = useState("benchmark_15d");
  const [asof, setAsof] = useState("2026-08-26");
  const [simMode, setSimMode] = useState<"day" | "window">("day");
  const [labMode, setLabMode] = useState<LabMode>("session");
  const [maxPositions, setMaxPositions] = useState(3);
  const [barInterval, setBarInterval] = useState<BarInterval>("5m");
  const [capital, setCapital] = useState(10000);
  const [tableView, setTableView] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState("");
  const [benchmarks, setBenchmarks] = useState<BenchWindow[]>([]);
  const [learning, setLearning] = useState<any>(null);
  const [strategies, setStrategies] = useState<any[]>([]);
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [runResult, setRunResult] = useState<any>(null);
  const [selectedTradeId, setSelectedTradeId] = useState<string | null>(null);
  const [bookFilter, setBookFilter] = useState<{ lane: string; pnl: string; q: string }>({
    lane: "all",
    pnl: "all",
    q: "",
  });
  const [replay, setReplay] = useState<{
    bars: PricePoint[];
    markers: TradeMarker[];
    trade: TradeRow;
    bar_interval?: string;
  } | null>(null);

  async function refreshMeta() {
    const [b, l, t, s] = await Promise.all([
      apiFetch<{ windows: BenchWindow[] }>("/exec/hybrid/benchmarks"),
      apiFetch<any>("/exec/hybrid/learning?limit=120"),
      apiFetch<{ trades: TradeRow[] }>("/exec/hybrid/trades?limit=120"),
      apiFetch<{ strategies: any[] }>(`/exec/hybrid/strategies?lane=${lane}`),
    ]);
    setBenchmarks(b.windows || []);
    setLearning(l);
    setTrades(t.trades || []);
    setStrategies(s.strategies || []);
    setLastRefresh(new Date().toLocaleTimeString());
  }

  useEffect(() => {
    refreshMeta().catch((e) => setError(String(e.message || e)));
  }, [lane]);

  useEffect(() => {
    const id = window.setInterval(() => {
      if (busy) return;
      refreshMeta().catch(() => undefined);
    }, 8000);
    return () => window.clearInterval(id);
  }, [busy, lane]);

  const blotterTrades: TradeRow[] = useMemo(() => runResult?.trades || [], [runResult]);

  const ladder = useMemo(
    () => runResult?.universe_ladder || runResult?.ticker_ranks || [],
    [runResult]
  );

  const filteredBook = useMemo(() => {
    return trades.filter((t) => {
      if (bookFilter.lane !== "all" && t.lane !== bookFilter.lane) return false;
      if (bookFilter.pnl === "win" && !(Number(t.pnl_pct) > 0)) return false;
      if (bookFilter.pnl === "loss" && !(Number(t.pnl_pct) < 0)) return false;
      if (bookFilter.q && !(t.ticker || "").toLowerCase().includes(bookFilter.q.toLowerCase())) return false;
      return true;
    });
  }, [trades, bookFilter]);

  async function openTrade(id: string, inline?: TradeRow) {
    setSelectedTradeId(id);
    if (inline?.bars?.length) {
      setReplay({
        bars: barsToPrices(inline.bars),
        markers: inline.markers || [],
        trade: inline,
        bar_interval: inline.bar_interval || barInterval,
      });
      return;
    }
    setBusy(true);
    try {
      const res = await apiFetch<{
        trade: TradeRow;
        bars: PricePoint[];
        markers: TradeMarker[];
        bar_interval?: string;
      }>(`/exec/hybrid/trades/${encodeURIComponent(id)}?bar_interval=${barInterval}`);
      setReplay({
        bars: (res.bars || []).map((b) => ({ ...b, close: Number(b.close) })),
        markers: res.markers || [],
        trade: { ...res.trade, bars: res.bars },
        bar_interval: res.bar_interval,
      });
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runSim() {
    setBusy(true);
    setError(null);
    setReplay(null);
    setLabMode("session");
    try {
      const q =
        simMode === "window"
          ? `/exec/hybrid-sim?window_id=${encodeURIComponent(windowId)}&lane=${lane}&capital=${capital}`
          : `/exec/hybrid-sim?asof=${encodeURIComponent(asof)}&lane=${lane}&capital=${capital}&max_positions=${maxPositions}&bar_interval=${barInterval}`;
      const res = await apiFetch<any>(q, { method: "POST" });
      if (res.error) throw new Error(res.error);
      setRunResult(res);
      await refreshMeta();
      const first = (res.trades || [])[0];
      if (first) {
        const tid = String(first.trade_id || `${asof}-${first.ticker}`);
        setSelectedTradeId(tid);
        if (first.bars?.length) {
          setReplay({
            bars: barsToPrices(first.bars),
            markers: first.markers || [],
            trade: first,
            bar_interval: first.bar_interval || barInterval,
          });
        }
      }
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  const ds = runResult?.decision_summary;
  const whyTickers = ds?.why_tickers || [];

  function ledgerFor(tradeId: string) {
    const led = runResult?.ledger || [];
    return led.filter((e: any) => String(e.trade_id || "") === tradeId);
  }

  return (
    <div className="hybrid-lab hybrid-terminal">
      <div className="page-intro hybrid-hero">
        <div>
          <h2>Hybrid Lab</h2>
          <p className="muted">
            Session desk · trade book · strategies — money put, confidence, OR-width, why picked. Auto-refresh{" "}
            {lastRefresh || "—"}.
          </p>
        </div>
        <div className="terminal-status">
          <span className={busy ? "pulse" : ""}>{busy ? "RUNNING" : "IDLE"}</span>
          <span className="muted">
            {barInterval} · {maxPositions} slots
          </span>
        </div>
      </div>

      {error && <p className="warn">{error}</p>}

      <HybridRunnerBar
        mode={simMode}
        lane={lane}
        asof={asof}
        windowId={windowId}
        benchmarks={benchmarks}
        capital={capital}
        maxPositions={maxPositions}
        barInterval={barInterval}
        busy={busy}
        tableView={tableView}
        onMode={setSimMode}
        onLane={setLane}
        onAsof={setAsof}
        onWindowId={setWindowId}
        onCapital={setCapital}
        onMaxPositions={setMaxPositions}
        onBarInterval={setBarInterval}
        onTableView={setTableView}
        onRun={runSim}
      />

      <HybridSessionTape
        runResult={runResult}
        capital={capital}
        lane={lane}
        blotterCount={blotterTrades.length}
      />

      <div className="segmented hybrid-modes">
        {(
          [
            ["session", "Session desk"],
            ["book", "Trade book"],
            ["strategies", "Strategies"],
          ] as [LabMode, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={labMode === id ? "active pressable" : "pressable"}
            onClick={() => setLabMode(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {labMode === "session" && (
        <div className="hybrid-session-stack">
          {(learning?.rules_briefing || runResult?.rules_briefing) && (
            <section className="hybrid-panel hybrid-rules-briefing">
              <h3>Rules ledger (read before trade)</h3>
              <p className="muted">
                {(runResult?.rules_briefing || learning?.rules_briefing)?.summary}
              </p>
              <ul className="hybrid-rules-list">
                {((runResult?.rules_briefing || learning?.rules_briefing)?.lines || [])
                  .slice(0, 12)
                  .map((line: string) => (
                    <li key={line}>{line}</li>
                  ))}
              </ul>
              {(runResult?.rules_learn || learning?.rules_ledger?.last_learned_asof) && (
                <p className="muted tiny">
                  Last learned:{" "}
                  {runResult?.rules_learn?.asof ||
                    learning?.rules_ledger?.last_learned_asof ||
                    "—"}
                  {runResult?.sitout ? " · SIT-OUT active" : ""}
                </p>
              )}
            </section>
          )}

          <StrategyDecisionCard
            decisionSummary={ds}
            chooser={runResult?.chooser}
            regime={runResult?.regime}
            strategyId={runResult?.strategy_id}
          />

          {whyTickers.length > 0 && (
            <section className="hybrid-panel">
              <h3>Why these tickers</h3>
              {tableView ? (
                <div className="table-scroll">
                  <table className="bb-table dense">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Ticker</th>
                        <th>Conf</th>
                        <th>OR%</th>
                        <th>Put ₹</th>
                        <th>Lev</th>
                        <th>U-rank</th>
                        <th>Signal</th>
                      </tr>
                    </thead>
                    <tbody>
                      {whyTickers.map((t: any) => (
                        <tr key={`${t.pick_order}-${t.ticker}`}>
                          <td>{t.pick_order}</td>
                          <td>
                            <strong>{t.ticker}</strong>
                          </td>
                          <td>{fmtNum(t.confidence, 3)}</td>
                          <td>{fmtNum((t.or_width_pct || 0) * 100, 3)}</td>
                          <td>{fmtInr(t.money_put)}</td>
                          <td>{fmtNum(t.leverage, 2)}x</td>
                          <td>{t.universe_rank ?? "—"}</td>
                          <td className="wrap">{t.signal_reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="metric-row wrap-gap">
                  {whyTickers.map((t: any) => (
                    <div key={`${t.pick_order}-${t.ticker}`} className="metric accent">
                      <span className="label">
                        #{t.pick_order} {t.ticker}
                      </span>
                      <span className="value">
                        conf {fmtNum(t.confidence, 3)} · put {fmtInr(t.money_put)} · {fmtNum(t.leverage, 2)}x
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          <UniverseLadderList ladder={ladder} tableView={tableView} />

          <section className="hybrid-panel">
            <h3>Session fills</h3>
            {!blotterTrades.length && <p className="muted">No fills yet — run a day sim.</p>}
            {tableView && blotterTrades.length > 0 ? (
              <div className="table-scroll tall">
                <table className="bb-table dense">
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Conf</th>
                      <th>Put ₹</th>
                      <th>PnL%</th>
                      <th>Lev</th>
                      <th>Why</th>
                    </tr>
                  </thead>
                  <tbody>
                    {blotterTrades.map((t) => {
                      const id = String(t.trade_id || t.id || "");
                      return (
                        <tr key={id} className={selectedTradeId === id ? "row-sel" : ""} onClick={() => openTrade(id, t)}>
                          <td>
                            <strong>{t.ticker}</strong>
                          </td>
                          <td>{fmtNum(t.confidence, 3)}</td>
                          <td>{fmtInr(t.money_put)}</td>
                          <td className={clsPnL(t.pnl_pct)}>{fmtPct(t.pnl_pct)}</td>
                          <td>{fmtNum(t.leverage, 2)}x</td>
                          <td className="wrap">{t.why_selected || t.signal_reason}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="panel-list">
                {blotterTrades.map((t) => {
                  const id = String(t.trade_id || t.id || "");
                  return (
                    <HybridTradeCard
                      key={id}
                      trade={t}
                      selected={selectedTradeId === id}
                      asofFallback={asof}
                      ledgerSlice={ledgerFor(id)}
                      onSelect={(tid, tr) => openTrade(tid, tr)}
                    />
                  );
                })}
              </div>
            )}
          </section>

          {runResult?.skipped?.length > 0 && (
            <section className="hybrid-panel">
              <h3>Skipped / rejected</h3>
              <div className="table-scroll">
                <table className="bb-table dense">
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Reason</th>
                      <th>Conf</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runResult.skipped.slice(0, 60).map((s: any, i: number) => (
                      <tr key={i}>
                        <td>{s.ticker || "—"}</td>
                        <td className="wrap">{s.reason}</td>
                        <td>{fmtNum(s.confidence, 3)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {runResult?.daily && <EquitySpark daily={runResult.daily} />}
        </div>
      )}

      {labMode === "book" && (
        <div className="hybrid-session-stack">
          <section className="hybrid-panel">
            <h3>Trade book filters</h3>
            <div className="runner-row dense">
              <label>
                Lane
                <select
                  value={bookFilter.lane}
                  onChange={(e) => setBookFilter((f) => ({ ...f, lane: e.target.value }))}
                >
                  <option value="all">all</option>
                  <option value="product">product</option>
                  <option value="stretch">stretch</option>
                  <option value="research">research</option>
                </select>
              </label>
              <label>
                PnL
                <select
                  value={bookFilter.pnl}
                  onChange={(e) => setBookFilter((f) => ({ ...f, pnl: e.target.value }))}
                >
                  <option value="all">all</option>
                  <option value="win">wins</option>
                  <option value="loss">losses</option>
                </select>
              </label>
              <label>
                Ticker
                <input
                  value={bookFilter.q}
                  placeholder="filter…"
                  onChange={(e) => setBookFilter((f) => ({ ...f, q: e.target.value }))}
                />
              </label>
            </div>
          </section>
          <div className="panel-list">
            {filteredBook.map((t) => {
              const id = String(t.trade_id || t.id || "");
              const merged = replay?.trade && String(replay.trade.trade_id || replay.trade.id) === id
                ? { ...t, ...replay.trade, bars: replay.bars }
                : t;
              return (
                <HybridTradeCard
                  key={id}
                  trade={merged}
                  selected={selectedTradeId === id}
                  onSelect={(tid) => openTrade(tid, t)}
                />
              );
            })}
            {!filteredBook.length && <p className="muted">No recorded hybrid trades match filters.</p>}
          </div>
          {replay?.bars?.length && selectedTradeId && !filteredBook.some((t) => (t.bars || []).length) && (
            <section className="hybrid-panel">
              <h3>Microscope · {replay.trade.ticker}</h3>
              <DetailPriceChart
                prices={replay.bars}
                height={320}
                markers={replay.markers}
                entryPrice={replay.trade.entry_price}
              />
            </section>
          )}
        </div>
      )}

      {labMode === "strategies" && (
        <StrategyRegistryPanel
          strategies={strategies}
          chooserState={learning?.chooser_state}
          learningCurve={learning?.learning_curve || []}
          daily={runResult?.daily}
        />
      )}
    </div>
  );
}
