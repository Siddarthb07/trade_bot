import { useState } from "react";
import { DetailPriceChart, MiniPriceChart, type PricePoint, type TradeMarker } from "../PriceChart";
import { barsToPrices, clsPnL, fmtInr, fmtNum, fmtPct } from "./format";

export type TradeRow = {
  id?: string;
  trade_id?: string;
  asof?: string;
  ticker?: string;
  lane?: string;
  strategy_id?: string;
  hybrid_strategy_id?: string;
  regime?: string;
  pnl?: number;
  pnl_pct?: number;
  fees?: number;
  entry_price?: number;
  exit_price?: number;
  entry_date?: string;
  exit_date?: string;
  exit_reason?: string;
  confidence?: number;
  or_width_pct?: number;
  or_width_bps?: number;
  leverage?: number;
  money_put?: number;
  money_returned?: number;
  entry_notional?: number;
  exit_notional?: number;
  bulk_entity?: string;
  bulk_score?: number;
  bulk_wr?: number;
  qty?: number;
  tp_pct?: number;
  sl_pct?: number;
  slot_capital?: number;
  target_notional?: number;
  signal_reason?: string;
  why_selected?: string;
  universe_rank?: number;
  pick_order?: number;
  guard_notes?: string[] | string;
  decision?: any;
  chooser?: any;
  sim_kwargs?: any;
  rank_row?: any;
  markers?: TradeMarker[];
  bars?: any[];
  bar_interval?: string;
};

type Props = {
  trade: TradeRow;
  selected?: boolean;
  asofFallback?: string;
  onSelect?: (id: string, trade: TradeRow) => void;
  ledgerSlice?: any[];
};

export default function HybridTradeCard({ trade, selected, asofFallback, onSelect, ledgerSlice }: Props) {
  const [open, setOpen] = useState(false);
  const id = String(trade.trade_id || trade.id || "");
  const prices: PricePoint[] = barsToPrices(trade.bars);
  const pnlColor = (trade.pnl_pct || 0) >= 0 ? "#4ade80" : "#f87171";

  function toggle() {
    onSelect?.(id, trade);
    setOpen((o) => !o);
  }

  return (
    <article
      className={`stock-panel hybrid-trade-card pressable ${selected ? "is-selected" : ""} ${open ? "is-expanded" : ""}`}
    >
      <div className="stock-chart-col" onClick={toggle}>
        {prices.length ? (
          <MiniPriceChart prices={prices} height={88} color={pnlColor} />
        ) : (
          <div className="chart-placeholder" style={{ height: 88 }}>
            No bars
          </div>
        )}
        <div className="chart-ticker">
          <span>{trade.ticker}</span>
          <span>{trade.bar_interval || "5m"}</span>
        </div>
      </div>
      <div className="stock-body">
        <button type="button" className="stock-head pressable flat" onClick={toggle}>
          <span className="rank">#{trade.pick_order || trade.universe_rank || "—"}</span>
          <div>
            <strong>
              {trade.ticker} · {trade.asof || asofFallback || ""}
            </strong>
            <div className="subline">
              {(trade.hybrid_strategy_id || trade.strategy_id || "—") + " · " + (trade.exit_reason || "—")}
            </div>
          </div>
        </button>
        <div className="metric-row">
          <div className="metric accent">
            <span className="label">Money put</span>
            <span className="value">{fmtInr(trade.money_put)}</span>
          </div>
          <div className="metric">
            <span className="label">Returned</span>
            <span className="value">{fmtInr(trade.money_returned)}</span>
          </div>
          <div className="metric">
            <span className="label">PnL</span>
            <span className={`value ${clsPnL(trade.pnl)}`}>
              {fmtInr(trade.pnl)} ({fmtPct(trade.pnl_pct)})
            </span>
          </div>
          <div className="metric">
            <span className="label">Conf</span>
            <span className="value">{fmtNum(trade.confidence, 3)}</span>
          </div>
          <div className="metric">
            <span className="label">OR%</span>
            <span className="value">{fmtNum((trade.or_width_pct || 0) * 100, 3)}</span>
          </div>
          <div className="metric">
            <span className="label">Lev</span>
            <span className="value">{fmtNum(trade.leverage, 2)}x</span>
          </div>
        </div>
        <div className="tags">
          {trade.lane && <span className={`tag lane-badge lane-${trade.lane}`}>{trade.lane}</span>}
          <span className="tag">qty {fmtNum(trade.qty, 2)}</span>
          <span className="tag">
            {fmtNum(trade.entry_price, 2)} → {fmtNum(trade.exit_price, 2)}
          </span>
        </div>
        {open && (
          <div className="hybrid-expand-body" onClick={(e) => e.stopPropagation()}>
            <p className="wrap">
              <strong>Why selected:</strong> {trade.why_selected || trade.signal_reason || "—"}
            </p>
            <p className="wrap muted">
              Guards:{" "}
              {Array.isArray(trade.guard_notes)
                ? trade.guard_notes.join(" | ")
                : trade.guard_notes || "—"}
            </p>
            <div className="metric-row">
              <div className="metric">
                <span className="label">Slot / target</span>
                <span className="value">
                  {fmtInr(trade.slot_capital)} / {fmtInr(trade.target_notional)}
                </span>
              </div>
              <div className="metric">
                <span className="label">TP / SL %</span>
                <span className="value">
                  {fmtNum(trade.tp_pct, 2)} / {fmtNum(trade.sl_pct, 2)}
                </span>
              </div>
              <div className="metric">
                <span className="label">Fees</span>
                <span className="value">{fmtInr(trade.fees)}</span>
              </div>
            </div>
            {prices.length > 0 && (
              <DetailPriceChart
                prices={prices}
                height={280}
                markers={trade.markers}
                entryPrice={trade.entry_price}
              />
            )}
            {ledgerSlice && ledgerSlice.length > 0 && (
              <div className="table-scroll">
                <table className="bb-table dense">
                  <thead>
                    <tr>
                      <th>Ts</th>
                      <th>Event</th>
                      <th>Notional</th>
                      <th>Cash</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledgerSlice.map((e, i) => (
                      <tr key={i}>
                        <td>{String(e.ts || "").slice(0, 19)}</td>
                        <td>{e.event}</td>
                        <td>{fmtInr(e.notional)}</td>
                        <td>{fmtInr(e.cash_after ?? e.cash)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <pre className="chooser-debug">
              {JSON.stringify(
                trade.decision || {
                  chooser: trade.chooser,
                  sim_kwargs: trade.sim_kwargs,
                  rank_row: trade.rank_row,
                },
                null,
                2
              )}
            </pre>
          </div>
        )}
      </div>
    </article>
  );
}
