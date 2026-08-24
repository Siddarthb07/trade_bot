import { useEffect, useState } from "react";
import { apiFetch } from "../api";

interface BookState {
  kill_switch: boolean;
  session_armed: boolean;
  exec_mode: string;
  max_notional_per_trade: number;
  max_open_notional: number;
  max_daily_loss: number;
  daily_realized_pnl: number;
  ladder_stage: number;
  open_positions: number;
}

interface ExecStatus {
  session: {
    ist_now: string;
    in_cash_open: boolean;
    should_flatten_in_day: boolean;
    us_regular_open: boolean;
    should_flatten_us_day: boolean;
  };
  books: Record<string, BookState>;
  last_order?: {
    id: string;
    ticker: string;
    market: string;
    status: string;
    created_at?: string;
  } | null;
}

interface OrderRow {
  id: string;
  market: string;
  ticker: string;
  side: string;
  qty: number;
  notional?: number;
  sized_notional?: number;
  status: string;
  reject_reason?: string;
  strategy_id?: string;
  predicted_prob?: number;
  broker?: string;
  book?: string;
  created_at?: string;
}

interface TapeItem {
  kind: string;
  id: string;
  ts?: string | null;
  market?: string;
  ticker?: string;
  side?: string;
  qty?: number;
  notional?: number;
  price?: number;
  status?: string;
  strategy_id?: string;
  predicted_prob?: number;
  reject_reason?: string;
  fee?: number;
}

interface SimTrade {
  trade_id: string;
  ticker: string;
  entry_date: string;
  exit_date: string;
  qty: number;
  entry_price: number;
  exit_price: number;
  entry_notional: number;
  exit_notional: number;
  fees: number;
  pnl: number;
  pnl_pct: number;
  exit_reason: string;
  confidence: number;
  money_put: number;
  money_returned: number;
  signal_reason?: string;
}

interface DaySim {
  asof: string;
  market: string;
  currency: string;
  capital_start: number;
  capital_end: number;
  realized_pnl: number;
  return_pct: number;
  n_trades: number;
  trades: SimTrade[];
  ledger: Array<Record<string, unknown>>;
  skipped: Array<Record<string, unknown>>;
  pnl_statement: {
    opening_cash: number;
    closing_cash: number;
    gross_pnl: number;
    fees_total: number;
    wins: number;
    losses: number;
    hit_rate_pct?: number | null;
    lines: Array<{
      ticker: string;
      put: number;
      returned: number;
      pnl: number;
      pnl_pct: number;
      entry: string;
      exit: string;
      exit_reason: string;
    }>;
  };
  disclaimer?: string;
}

export default function ExecPage() {
  const [status, setStatus] = useState<ExecStatus | null>(null);
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [tape, setTape] = useState<TapeItem[]>([]);
  const [market, setMarket] = useState<string>("");
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(true);
  const [simDate, setSimDate] = useState("2024-08-23");
  const [simCapital, setSimCapital] = useState(10000);
  const [simMarket, setSimMarket] = useState("IN");
  const [sim, setSim] = useState<DaySim | null>(null);
  const [simLoading, setSimLoading] = useState(false);

  async function load() {
    try {
      const q = market ? `?market=${market}&limit=100` : "?limit=100";
      const [s, o, live] = await Promise.all([
        apiFetch<ExecStatus>("/exec/status"),
        apiFetch<{ items: OrderRow[] }>(`/exec/orders${q}`),
        apiFetch<{ tape: TapeItem[] }>("/exec/live?limit=40").catch(() => ({ tape: [] })),
      ]);
      setStatus(s);
      setOrders(o.items || []);
      setTape(live.tape || []);
      setMsg("");
    } catch (e) {
      console.error(e);
      setMsg(String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 5_000);
    return () => clearInterval(t);
  }, [market]);

  async function arm() {
    await apiFetch("/exec/arm", { method: "POST", body: "{}" });
    setMsg("Sessions armed — live tape polling every 5s");
    load();
  }

  async function kill(m: string) {
    await apiFetch(`/exec/kill?market=${m}`, { method: "POST", body: "{}" });
    setMsg(`Kill ${m}`);
    load();
  }

  async function runDaySim() {
    setSimLoading(true);
    setMsg("");
    try {
      const q = new URLSearchParams({
        asof: simDate,
        capital: String(simCapital),
        market: simMarket,
        max_positions: "3",
      });
      const res = await apiFetch<DaySim>(`/exec/day-sim?${q}`, { method: "POST", body: "{}" });
      setSim(res);
      setMsg(`Day sim ${res.asof}: ${res.n_trades} trades · PnL ${res.currency} ${res.realized_pnl}`);
    } catch (e) {
      setMsg(String(e));
    } finally {
      setSimLoading(false);
    }
  }

  const cur = sim?.currency || "INR";
  const fmt = (n: number | undefined | null) =>
    n == null ? "—" : `${cur === "INR" ? "₹" : "$"}${Number(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

  return (
    <div className="page-stack">
      <section className="hero-banner">
        <div>
          <span className="eyebrow">Live</span>
          <h2>Live trading</h2>
          <p>Watch every order as it fills. Arm sessions for paper/live exec; run a ₹10k day replay below.</p>
        </div>
        <div className="hero-actions">
          <button type="button" className="btn" onClick={arm}>Arm sessions</button>
          <button type="button" className="btn btn-danger" onClick={() => kill("ALL")}>Kill ALL</button>
        </div>
      </section>

      {msg && <p className="muted">{msg}</p>}
      {loading && !status && <p>Loading…</p>}

      {status && (
        <section className="card">
          <h3>Session · live</h3>
          <p className="muted">IST {status.session.ist_now} · tape refreshes every 5s</p>
          <div className="stat-grid">
            <div>
              <span className="eyebrow">IN cash</span>
              <strong>{status.session.in_cash_open ? "OPEN" : "closed"}</strong>
            </div>
            <div>
              <span className="eyebrow">US regular</span>
              <strong>{status.session.us_regular_open ? "OPEN" : "closed"}</strong>
            </div>
            {Object.entries(status.books).map(([m, b]) => (
              <div key={m}>
                <span className="eyebrow">{m}</span>
                <strong>
                  {b.session_armed ? "armed" : "idle"} · {b.kill_switch ? "KILL" : b.exec_mode}
                </strong>
                <div className="muted">day PnL {b.daily_realized_pnl} · cap {b.max_notional_per_trade}</div>
              </div>
            ))}
          </div>
          {status.last_order && (
            <p className="muted">
              Last: {status.last_order.ticker} {status.last_order.market} · {status.last_order.status}
            </p>
          )}
        </section>
      )}

      <section className="card">
        <div className="row-between">
          <h3>Live tape</h3>
          <button type="button" className="btn-link" onClick={load}>Refresh now</button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Kind</th>
                <th>Mkt</th>
                <th>Ticker</th>
                <th>Side</th>
                <th>Qty / $</th>
                <th>Status</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {tape.map((t) => (
                <tr key={`${t.kind}-${t.id}`}>
                  <td>{t.ts?.slice(0, 19) || "—"}</td>
                  <td>{t.kind}</td>
                  <td>{t.market || "—"}</td>
                  <td>{t.ticker || "—"}</td>
                  <td>{t.side || "—"}</td>
                  <td>
                    {t.qty ?? "—"}
                    {t.notional != null ? ` · ${t.notional}` : t.price != null ? ` @ ${t.price}` : ""}
                  </td>
                  <td>{t.status || "fill"}</td>
                  <td className="muted">{t.reject_reason || t.strategy_id || ""}</td>
                </tr>
              ))}
              {!tape.length && (
                <tr>
                  <td colSpan={8} className="muted">
                    No live fills yet — arm sessions and wait for signals, or run a day sim below.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h3>Day sim — ₹10k paper replay</h3>
        <p className="muted">
          Pick a date (default 2024-08-23). Bot allocates up to 3 IN names from adaptive setups, shows every rupee put/returned and full PnL.
        </p>
        <div className="row-between" style={{ gap: "0.75rem", flexWrap: "wrap" }}>
          <label>
            Date{" "}
            <input type="date" value={simDate} onChange={(e) => setSimDate(e.target.value)} />
          </label>
          <label>
            Capital{" "}
            <input
              type="number"
              value={simCapital}
              min={1000}
              step={1000}
              onChange={(e) => setSimCapital(Number(e.target.value) || 10000)}
            />
          </label>
          <label>
            Market{" "}
            <select value={simMarket} onChange={(e) => setSimMarket(e.target.value)}>
              <option value="IN">IN (INR)</option>
              <option value="US">US (USD)</option>
            </select>
          </label>
          <button type="button" className="btn" disabled={simLoading} onClick={runDaySim}>
            {simLoading ? "Simulating…" : "Run day sim"}
          </button>
        </div>

        {sim && (
          <>
            <div className="stat-grid" style={{ marginTop: "1rem" }}>
              <div>
                <span className="eyebrow">Start</span>
                <strong>{fmt(sim.capital_start)}</strong>
              </div>
              <div>
                <span className="eyebrow">End</span>
                <strong>{fmt(sim.capital_end)}</strong>
              </div>
              <div>
                <span className="eyebrow">Realized PnL</span>
                <strong style={{ color: sim.realized_pnl >= 0 ? "inherit" : "#b33" }}>
                  {fmt(sim.realized_pnl)} ({sim.return_pct}%)
                </strong>
              </div>
              <div>
                <span className="eyebrow">Hit rate</span>
                <strong>
                  {sim.pnl_statement.hit_rate_pct != null ? `${sim.pnl_statement.hit_rate_pct}%` : "—"} ·{" "}
                  {sim.pnl_statement.wins}W/{sim.pnl_statement.losses}L
                </strong>
              </div>
            </div>

            <h4>PnL statement</h4>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Ticker</th>
                    <th>Money put</th>
                    <th>Returned</th>
                    <th>PnL</th>
                    <th>%</th>
                    <th>Entry → exit</th>
                    <th>Exit why</th>
                  </tr>
                </thead>
                <tbody>
                  {sim.pnl_statement.lines.map((l) => (
                    <tr key={`${l.ticker}-${l.entry}`}>
                      <td>{l.ticker}</td>
                      <td>{fmt(l.put)}</td>
                      <td>{fmt(l.returned)}</td>
                      <td style={{ color: l.pnl >= 0 ? "inherit" : "#b33" }}>{fmt(l.pnl)}</td>
                      <td>{l.pnl_pct}%</td>
                      <td>
                        {l.entry} → {l.exit}
                      </td>
                      <td>{l.exit_reason}</td>
                    </tr>
                  ))}
                  {!sim.pnl_statement.lines.length && (
                    <tr>
                      <td colSpan={7} className="muted">
                        No trades that day — setups did not clear the gate.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            <h4>Cash ledger (every move)</h4>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Event</th>
                    <th>Ticker</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Notional</th>
                    <th>Cash after</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {sim.ledger.map((row, i) => (
                    <tr key={i}>
                      <td>{String(row.ts ?? "—")}</td>
                      <td>{String(row.event ?? "—")}</td>
                      <td>{String(row.ticker ?? "—")}</td>
                      <td>{row.qty != null ? String(row.qty) : "—"}</td>
                      <td>{row.price != null ? String(row.price) : "—"}</td>
                      <td>{row.notional != null ? fmt(Number(row.notional)) : "—"}</td>
                      <td>{row.cash_after != null ? fmt(Number(row.cash_after)) : row.cash != null ? fmt(Number(row.cash)) : "—"}</td>
                      <td className="muted">
                        {row.pnl != null
                          ? `PnL ${fmt(Number(row.pnl))}`
                          : String(row.signal_reason || row.exit_reason || row.note || "")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {sim.disclaimer && <p className="muted">{sim.disclaimer}</p>}
          </>
        )}
      </section>

      <section className="card">
        <div className="row-between">
          <h3>Order blotter</h3>
          <select value={market} onChange={(e) => setMarket(e.target.value)}>
            <option value="">All</option>
            <option value="IN">IN</option>
            <option value="US">US</option>
          </select>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>When</th>
                <th>Mkt</th>
                <th>Ticker</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Notional</th>
                <th>Prob</th>
                <th>Strategy</th>
                <th>Status</th>
                <th>Why</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id}>
                  <td>{o.created_at?.slice(0, 19) || "—"}</td>
                  <td>{o.market}</td>
                  <td>{o.ticker}</td>
                  <td>{o.side}</td>
                  <td>{o.qty}</td>
                  <td>{o.sized_notional ?? o.notional ?? "—"}</td>
                  <td>{o.predicted_prob != null ? `${(o.predicted_prob * 100).toFixed(0)}%` : "—"}</td>
                  <td>{o.strategy_id || "—"}</td>
                  <td>{o.status}</td>
                  <td className="muted">{o.reject_reason || o.book || ""}</td>
                </tr>
              ))}
              {!orders.length && (
                <tr>
                  <td colSpan={10} className="muted">No orders yet — arm sessions and wait for signals.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
