import { useEffect, useMemo, useState } from "react";
import { apiFetch } from "../api";
import HybridRunnerBar from "../components/hybrid/HybridRunnerBar";
import HybridSessionTape from "../components/hybrid/HybridSessionTape";
import UniverseLadderList from "../components/hybrid/UniverseLadderList";
import HybridTradeCard, { type TradeRow } from "../components/hybrid/HybridTradeCard";
import { EquitySpark } from "../components/hybrid/StrategyRegistryPanel";
import {
  type BarInterval,
  type LabMode,
  barsToPrices,
  clsPnL,
  fmtInr,
  fmtNum,
  fmtPct,
} from "../components/hybrid/format";
import { DetailPriceChart, type PricePoint, type TradeMarker } from "../components/PriceChart";

type BenchWindow = { id: string; label?: string };

const STRATEGY = "copy_bulk_pro";
const LANE = "product" as const;

function investAmount(t: TradeRow | Record<string, unknown>): number {
  const v = t.money_put ?? t.entry_notional ?? (t as any).target_notional ?? 0;
  return Number(v) || 0;
}

function returnedAmount(t: TradeRow | Record<string, unknown>): number {
  const v = t.money_returned ?? t.exit_notional ?? 0;
  return Number(v) || 0;
}

type InvestAgg = {
  ticker: string;
  n_trades: number;
  invested_total: number;
  returned_total: number;
  pnl_total: number;
  trades: TradeRow[];
};

type ForwardDraft = {
  balance: number;
  capital_use_frac: number;
  max_positions: number;
  soft_trail_arm_pct: number;
  soft_trail_pct: number;
  status: "idle" | "running" | "paused" | "placeholder";
  note: string;
};

export default function GodFatherPage() {
  const [windowId, setWindowId] = useState("benchmark_15d");
  const [asof, setAsof] = useState("2026-08-28");
  const [simMode, setSimMode] = useState<"day" | "window">("day");
  const [labMode, setLabMode] = useState<LabMode>("session");
  const [maxPositions, setMaxPositions] = useState(2);
  const [barInterval, setBarInterval] = useState<BarInterval>("5m");
  const [capital, setCapital] = useState(10000);
  const [tableView, setTableView] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState("");
  const [benchmarks, setBenchmarks] = useState<BenchWindow[]>([]);
  const [learning, setLearning] = useState<any>(null);
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [runResult, setRunResult] = useState<any>(null);
  const [selectedTradeId, setSelectedTradeId] = useState<string | null>(null);
  const [bookFilter, setBookFilter] = useState<{ pnl: string; q: string }>({
    pnl: "all",
    q: "",
  });
  const [replay, setReplay] = useState<{
    bars: PricePoint[];
    markers: TradeMarker[];
    trade: TradeRow;
    bar_interval?: string;
  } | null>(null);
  const [forward, setForward] = useState<ForwardDraft>({
    balance: 10000,
    capital_use_frac: 0.85,
    max_positions: 2,
    soft_trail_arm_pct: 0.025,
    soft_trail_pct: 0.01,
    status: "placeholder",
    note: "Forward API not connected — local draft only.",
  });

  async function refreshMeta() {
    const [b, l, t] = await Promise.all([
      apiFetch<{ windows: BenchWindow[] }>("/exec/hybrid/benchmarks"),
      apiFetch<any>("/exec/hybrid/learning?limit=120"),
      apiFetch<{ trades: TradeRow[] }>("/exec/hybrid/trades?limit=500"),
    ]);
    setBenchmarks(b.windows || []);
    setLearning(l);
    setTrades(
      (t.trades || []).filter(
        (row) =>
          row.hybrid_strategy_id === STRATEGY ||
          row.strategy_id === STRATEGY ||
          String(row.signal_reason || "").includes("copy_bulk_pro")
      )
    );
    setLastRefresh(new Date().toLocaleTimeString());
  }

  useEffect(() => {
    refreshMeta().catch((e) => setError(String(e.message || e)));
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => {
      if (busy) return;
      refreshMeta().catch(() => undefined);
    }, 8000);
    return () => window.clearInterval(id);
  }, [busy]);

  const blotterTrades: TradeRow[] = useMemo(() => runResult?.trades || [], [runResult]);

  /** Prefer live session fills; else full copy-pro book. */
  const investSource: TradeRow[] = useMemo(() => {
    if (blotterTrades.length) return blotterTrades;
    return trades;
  }, [blotterTrades, trades]);

  const investedByTicker: InvestAgg[] = useMemo(() => {
    const map = new Map<string, InvestAgg>();
    for (const t of investSource) {
      const ticker = String(t.ticker || "—");
      const cur = map.get(ticker) || {
        ticker,
        n_trades: 0,
        invested_total: 0,
        returned_total: 0,
        pnl_total: 0,
        trades: [],
      };
      cur.n_trades += 1;
      cur.invested_total += investAmount(t);
      cur.returned_total += returnedAmount(t);
      cur.pnl_total += Number(t.pnl) || 0;
      cur.trades.push(t);
      map.set(ticker, cur);
    }
    return Array.from(map.values()).sort((a, b) => b.invested_total - a.invested_total);
  }, [investSource]);

  const investedTotal = useMemo(
    () => investedByTicker.reduce((s, r) => s + r.invested_total, 0),
    [investedByTicker]
  );

  const ladder = useMemo(
    () => runResult?.universe_ladder || runResult?.ticker_ranks || runResult?.bulk_picks || [],
    [runResult]
  );

  const filteredBook = useMemo(() => {
    return trades.filter((t) => {
      if (bookFilter.pnl === "win" && !(Number(t.pnl_pct) > 0)) return false;
      if (bookFilter.pnl === "loss" && !(Number(t.pnl_pct) < 0)) return false;
      if (bookFilter.q && !(t.ticker || "").toLowerCase().includes(bookFilter.q.toLowerCase())) {
        return false;
      }
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
      const base =
        simMode === "window"
          ? `/exec/hybrid-sim?window_id=${encodeURIComponent(windowId)}&lane=${LANE}&capital=${capital}`
          : `/exec/hybrid-sim?asof=${encodeURIComponent(asof)}&lane=${LANE}&capital=${capital}&max_positions=${maxPositions}&bar_interval=${barInterval}`;
      const q = `${base}&force_strategy=${STRATEGY}`;
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
        } else {
          openTrade(tid, first).catch(() => undefined);
        }
      }
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  const ds = runResult?.decision_summary;
  const whyTickers = ds?.why_tickers || runResult?.why_tickers || [];
  const picks = runResult?.bulk_picks || runResult?.picks || ds?.bulk_picks || [];

  function ledgerFor(tradeId: string) {
    const led = runResult?.ledger || [];
    return led.filter((e: any) => String(e.trade_id || "") === tradeId);
  }

  async function callForward(action: "status" | "balance" | "start" | "pause" | "flatten") {
    setBusy(true);
    setError(null);
    try {
      if (action === "status") {
        const res = await apiFetch<any>("/exec/godfather/forward/status");
        setForward((f) => ({
          ...f,
          status: res.placeholder ? "placeholder" : res.status || "idle",
          note: res.disclaimer || "Status ok.",
          balance: res.balance ?? f.balance,
        }));
        return;
      }
      if (action === "balance") {
        const res = await apiFetch<any>("/exec/godfather/forward/balance", {
          method: "POST",
          body: JSON.stringify({ balance: forward.balance }),
        });
        setForward((f) => ({
          ...f,
          status: "placeholder",
          note: res.disclaimer || `Draft balance ${res.accepted_balance}`,
        }));
        setCapital(Number(forward.balance) || capital);
        return;
      }
      const res = await apiFetch<any>(`/exec/godfather/forward/${action}`, {
        method: "POST",
        body: JSON.stringify({
          balance: forward.balance,
          capital_use_frac: forward.capital_use_frac,
          max_positions: forward.max_positions,
          soft_trail_arm_pct: forward.soft_trail_arm_pct,
          soft_trail_pct: forward.soft_trail_pct,
          strategy_id: STRATEGY,
        }),
      });
      setForward((f) => ({
        ...f,
        status: "placeholder",
        note: res.disclaimer || `${action} acknowledged (placeholder).`,
      }));
    } catch (e: any) {
      setError(e.message || String(e));
      setForward((f) => ({
        ...f,
        status: "placeholder",
        note: `API unreachable for ${action} — local draft only.`,
      }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="hybrid-lab hybrid-terminal godfather-desk">
      <div className="page-intro hybrid-hero">
        <div>
          <h2>GodFather</h2>
          <p className="muted">
            copy_bulk_pro desk · why picked · money put · exit cause · candle replay. Paper/session-sim
            only (~30 bps RT modeled). Auto-refresh {lastRefresh || "—"}.
          </p>
        </div>
        <div className="terminal-status">
          <span className={busy ? "pulse" : ""}>{busy ? "RUNNING" : "IDLE"}</span>
          <span className="muted">
            {STRATEGY} · {barInterval} · {maxPositions} slots
          </span>
        </div>
      </div>

      {error && <p className="warn">{error}</p>}

      <HybridRunnerBar
        mode={simMode}
        lane={LANE}
        asof={asof}
        windowId={windowId}
        benchmarks={benchmarks}
        capital={capital}
        maxPositions={maxPositions}
        barInterval={barInterval}
        busy={busy}
        tableView={tableView}
        hideLane
        runLabel="Run copy-pro sim"
        onMode={setSimMode}
        onLane={() => undefined}
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
        lane={LANE}
        blotterCount={blotterTrades.length}
      />

      <div className="segmented hybrid-modes">
        {(
          [
            ["session", "Session"],
            ["book", "Trade book"],
            ["strategies", "Invested"],
            ["forward", "Forward"],
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

      {/* Always-on invested strip under tape */}
      <section className="hybrid-panel gf-invested-strip">
        <h3>
          Every stock invested
          <span className="muted" style={{ fontWeight: 400, marginLeft: 8 }}>
            {investedByTicker.length} tickers · {investSource.length} fills · put {fmtInr(investedTotal)}
            {blotterTrades.length ? " · this session" : " · book"}
          </span>
        </h3>
        {!investSource.length ? (
          <p className="muted">No fills yet — run a day/window sim to see every stock and ₹ put.</p>
        ) : (
          <div className="table-scroll tall">
            <table className="bb-table dense">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Date</th>
                  <th>Ticker</th>
                  <th>Invested ₹</th>
                  <th>Returned ₹</th>
                  <th>Qty</th>
                  <th>Lev</th>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th>PnL</th>
                  <th>Exit reason</th>
                </tr>
              </thead>
              <tbody>
                {investSource.map((t, i) => {
                  const id = String(t.trade_id || t.id || `${t.asof}-${t.ticker}-${i}`);
                  return (
                    <tr
                      key={id}
                      className={selectedTradeId === id ? "row-sel" : ""}
                      onClick={() => openTrade(id, t)}
                      style={{ cursor: "pointer" }}
                    >
                      <td>{i + 1}</td>
                      <td>{t.asof || t.entry_date || "—"}</td>
                      <td>
                        <strong>{t.ticker}</strong>
                      </td>
                      <td>{fmtInr(investAmount(t))}</td>
                      <td>{fmtInr(returnedAmount(t))}</td>
                      <td>{fmtNum(t.qty, 2)}</td>
                      <td>{fmtNum(t.leverage, 2)}x</td>
                      <td>{fmtNum(t.entry_price, 2)}</td>
                      <td>{fmtNum(t.exit_price, 2)}</td>
                      <td className={clsPnL(t.pnl)}>
                        {fmtInr(t.pnl)} ({fmtPct(t.pnl_pct)})
                      </td>
                      <td className="wrap">{t.exit_reason || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {labMode === "session" && (
        <div className="hybrid-session-stack">
          <section className="hybrid-panel hybrid-rules-briefing">
            <h3>Strategy lock</h3>
            <p className="muted">
              Forced <strong>{STRATEGY}</strong> (product). Copies prior-session NSE bulk/block BUYs,
              max lev ≤5×, soft trail 2.5%/1%, selective 2nd slot. Not ORB chooser rotation.
            </p>
            {(learning?.rules_briefing || runResult?.rules_briefing) && (
              <>
                <p className="muted">
                  {(runResult?.rules_briefing || learning?.rules_briefing)?.summary}
                </p>
                <ul className="hybrid-rules-list">
                  {((runResult?.rules_briefing || learning?.rules_briefing)?.lines || [])
                    .slice(0, 8)
                    .map((line: string) => (
                      <li key={line}>{line}</li>
                    ))}
                </ul>
              </>
            )}
          </section>

          {(picks.length > 0 || whyTickers.length > 0) && (
            <section className="hybrid-panel">
              <h3>Why these tickers</h3>
              {picks.length > 0 && (
                <div className="table-scroll">
                  <table className="bb-table dense">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Ticker</th>
                        <th>Score</th>
                        <th>WR</th>
                        <th>Deal ₹</th>
                        <th>Entity</th>
                      </tr>
                    </thead>
                    <tbody>
                      {picks.slice(0, 12).map((p: any, i: number) => (
                        <tr key={`${p.ticker}-${i}`}>
                          <td>{i + 1}</td>
                          <td>
                            <strong>{p.ticker}</strong>
                          </td>
                          <td>{fmtNum(p.score, 3)}</td>
                          <td>{fmtNum(p.win_rate_eff ?? p.win_rate, 3)}</td>
                          <td>{fmtInr(p.value)}</td>
                          <td className="wrap">{p.entity_normalized || p.entity || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {whyTickers.length > 0 && (
                <div className="metric-row wrap-gap" style={{ marginTop: 12 }}>
                  {whyTickers.map((t: any) => (
                    <div key={`${t.pick_order}-${t.ticker}`} className="metric accent">
                      <span className="label">
                        #{t.pick_order} {t.ticker}
                      </span>
                      <span className="value">
                        conf {fmtNum(t.confidence, 3)} · put {fmtInr(t.money_put)} ·{" "}
                        {fmtNum(t.leverage, 2)}x
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
                      <th>Put ₹</th>
                      <th>Returned</th>
                      <th>PnL</th>
                      <th>Lev</th>
                      <th>Exit</th>
                      <th>Why</th>
                    </tr>
                  </thead>
                  <tbody>
                    {blotterTrades.map((t) => {
                      const id = String(t.trade_id || t.id || "");
                      return (
                        <tr
                          key={id}
                          className={selectedTradeId === id ? "row-sel" : ""}
                          onClick={() => openTrade(id, t)}
                        >
                          <td>
                            <strong>{t.ticker}</strong>
                          </td>
                          <td>{fmtInr(t.money_put ?? t.entry_notional)}</td>
                          <td>{fmtInr(t.money_returned ?? t.exit_notional)}</td>
                          <td className={clsPnL(t.pnl)}>
                            {fmtInr(t.pnl)} ({fmtPct(t.pnl_pct)})
                          </td>
                          <td>{fmtNum(t.leverage, 2)}x</td>
                          <td>{t.exit_reason || "—"}</td>
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

          {replay?.bars?.length ? (
            <section className="hybrid-panel">
              <h3>
                Candle replay · {replay.trade.ticker} · {replay.bar_interval || barInterval}
              </h3>
              <p className="muted wrap">
                Entry {fmtNum(replay.trade.entry_price, 2)} → exit {fmtNum(replay.trade.exit_price, 2)} ·{" "}
                {replay.trade.exit_reason || "—"} · put{" "}
                {fmtInr(replay.trade.money_put ?? (replay.trade as any).entry_notional)}
              </p>
              <DetailPriceChart
                prices={replay.bars}
                height={340}
                markers={replay.markers}
                entryPrice={replay.trade.entry_price}
              />
              <p className="wrap muted" style={{ marginTop: 8 }}>
                <strong>Why:</strong> {replay.trade.why_selected || replay.trade.signal_reason || "—"}
              </p>
            </section>
          ) : null}

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
            <h3>Trade book · {STRATEGY}</h3>
            <div className="runner-row dense">
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
              const merged =
                replay?.trade && String(replay.trade.trade_id || replay.trade.id) === id
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
            {!filteredBook.length && (
              <p className="muted">No copy_bulk_pro trades in the book yet — run a session.</p>
            )}
          </div>
          {replay?.bars?.length && selectedTradeId && (
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
        <div className="hybrid-session-stack">
          <section className="hybrid-panel">
            <h3>By ticker · total invested</h3>
            <p className="muted">
              Rollup of every fill GodFather put money into
              {blotterTrades.length ? " (this session overrides book while a run is loaded)" : " (trade book)"}.
            </p>
            {!investedByTicker.length ? (
              <p className="muted">Nothing invested yet.</p>
            ) : (
              <div className="table-scroll tall">
                <table className="bb-table dense">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Ticker</th>
                      <th>Fills</th>
                      <th>Total invested ₹</th>
                      <th>Total returned ₹</th>
                      <th>Net PnL ₹</th>
                      <th>Avg put / fill</th>
                    </tr>
                  </thead>
                  <tbody>
                    {investedByTicker.map((row, i) => (
                      <tr key={row.ticker}>
                        <td>{i + 1}</td>
                        <td>
                          <strong>{row.ticker}</strong>
                        </td>
                        <td>{row.n_trades}</td>
                        <td>{fmtInr(row.invested_total)}</td>
                        <td>{fmtInr(row.returned_total)}</td>
                        <td className={clsPnL(row.pnl_total)}>{fmtInr(row.pnl_total)}</td>
                        <td>{fmtInr(row.invested_total / Math.max(1, row.n_trades))}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={3}>
                        <strong>All tickers</strong>
                      </td>
                      <td>
                        <strong>{fmtInr(investedTotal)}</strong>
                      </td>
                      <td>
                        <strong>
                          {fmtInr(investedByTicker.reduce((s, r) => s + r.returned_total, 0))}
                        </strong>
                      </td>
                      <td className={clsPnL(investedByTicker.reduce((s, r) => s + r.pnl_total, 0))}>
                        <strong>
                          {fmtInr(investedByTicker.reduce((s, r) => s + r.pnl_total, 0))}
                        </strong>
                      </td>
                      <td />
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </section>

          <section className="hybrid-panel">
            <h3>Per-fill breakdown</h3>
            <div className="table-scroll tall">
              <table className="bb-table dense">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Ticker</th>
                    <th>Invested ₹</th>
                    <th>Slot capital</th>
                    <th>Qty</th>
                    <th>Lev</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {investSource.map((t, i) => {
                    const id = String(t.trade_id || t.id || `${t.asof}-${t.ticker}-${i}`);
                    return (
                      <tr key={id} onClick={() => openTrade(id, t)} style={{ cursor: "pointer" }}>
                        <td>{t.asof || t.entry_date || "—"}</td>
                        <td>
                          <strong>{t.ticker}</strong>
                        </td>
                        <td>{fmtInr(investAmount(t))}</td>
                        <td>{fmtInr(t.slot_capital)}</td>
                        <td>{fmtNum(t.qty, 2)}</td>
                        <td>{fmtNum(t.leverage, 2)}x</td>
                        <td className="wrap">{t.why_selected || t.signal_reason || "—"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}

      {labMode === "forward" && (
        <div className="hybrid-session-stack">
          <section className="hybrid-panel">
            <h3>Forward test controls</h3>
            <p className="muted">
              Placeholders for live/forward balance control. Status: <strong>{forward.status}</strong>
            </p>
            <div className="runner-row dense">
              <label>
                Balance ₹
                <input
                  type="number"
                  value={forward.balance}
                  min={1000}
                  step={1000}
                  onChange={(e) =>
                    setForward((f) => ({
                      ...f,
                      balance: Number(e.target.value) || 10000,
                      status: "placeholder",
                      note: "Local draft — click Start or Refresh to hit API stubs.",
                    }))
                  }
                />
              </label>
              <label>
                Capital use
                <input
                  type="number"
                  value={forward.capital_use_frac}
                  min={0.1}
                  max={1}
                  step={0.05}
                  onChange={(e) =>
                    setForward((f) => ({
                      ...f,
                      capital_use_frac: Number(e.target.value) || 0.85,
                    }))
                  }
                />
              </label>
              <label>
                Positions
                <select
                  value={forward.max_positions}
                  onChange={(e) =>
                    setForward((f) => ({
                      ...f,
                      max_positions: Number(e.target.value) || 2,
                    }))
                  }
                >
                  {[1, 2, 3].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Trail arm
                <input
                  type="number"
                  value={forward.soft_trail_arm_pct}
                  step={0.005}
                  onChange={(e) =>
                    setForward((f) => ({
                      ...f,
                      soft_trail_arm_pct: Number(e.target.value) || 0.025,
                    }))
                  }
                />
              </label>
              <label>
                Trail give
                <input
                  type="number"
                  value={forward.soft_trail_pct}
                  step={0.005}
                  onChange={(e) =>
                    setForward((f) => ({
                      ...f,
                      soft_trail_pct: Number(e.target.value) || 0.01,
                    }))
                  }
                />
              </label>
            </div>
            <div className="runner-row dense" style={{ marginTop: 12 }}>
              <button
                type="button"
                className="primary pressable"
                disabled={busy}
                onClick={() => callForward("start")}
              >
                Start session
              </button>
              <button type="button" className="pressable" disabled={busy} onClick={() => callForward("pause")}>
                Pause
              </button>
              <button type="button" className="pressable" disabled={busy} onClick={() => callForward("flatten")}>
                Flatten
              </button>
              <button type="button" className="pressable" disabled={busy} onClick={() => callForward("status")}>
                Refresh status
              </button>
              <button type="button" className="pressable" disabled={busy} onClick={() => callForward("balance")}>
                Push balance
              </button>
            </div>
            <p className="warn" style={{ marginTop: 12 }}>
              {forward.note}
            </p>
            <p className="muted tiny">
              Planned routes: <code>/exec/godfather/forward/status</code>,{" "}
              <code>/exec/godfather/forward/balance</code>,{" "}
              <code>/exec/godfather/forward/start|pause|flatten</code>. Session sim above still uses
              existing <code>/exec/hybrid-sim?force_strategy=copy_bulk_pro</code>.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
