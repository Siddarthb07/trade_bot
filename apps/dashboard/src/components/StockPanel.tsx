import { Link } from "react-router-dom";
import { MiniPriceChart, PricePoint, TrendInfo } from "./PriceChart";
import { fmtExp, fmtPct, fmtValue, tierClass } from "../utils/format";

export interface Metric {
  label: string;
  value: string;
  accent?: boolean;
}

export default function StockPanel({
  rank,
  ticker,
  market,
  signalId,
  headline,
  subline,
  tier,
  metrics,
  tags,
  note,
  prices,
  trend,
  chartLoading,
}: {
  rank?: number;
  ticker: string;
  market: string;
  signalId?: string | null;
  headline: string;
  subline?: string;
  tier?: string;
  metrics: Metric[];
  tags?: string[];
  note?: string;
  prices?: PricePoint[];
  trend?: TrendInfo;
  chartLoading?: boolean;
}) {
  return (
    <article className="stock-panel">
      <div className="stock-chart-col">
        {chartLoading ? (
          <div className="chart-placeholder">Loading chart…</div>
        ) : (
          <MiniPriceChart prices={prices || []} trend={trend} />
        )}
        <div className="chart-ticker">
          {signalId ? <Link to={`/signals/${signalId}`}>{ticker}</Link> : ticker}
          <span>{market}</span>
        </div>
      </div>

      <div className="stock-body">
        <div className="stock-head">
          {rank != null && <span className="rank">#{rank}</span>}
          <div>
            <h3>{headline}</h3>
            {subline && <p className="subline">{subline}</p>}
          </div>
          {tier && <span className={tierClass(tier)}>{tier}</span>}
        </div>

        {note && <p className="stock-note">{note}</p>}

        <div className="metric-row">
          {metrics.map((m) => (
            <div key={m.label} className={`metric${m.accent ? " accent" : ""}`}>
              <span>{m.label}</span>
              <strong>{m.value}</strong>
            </div>
          ))}
        </div>

        <div className="stock-foot">
          <div className="tags">
            {tags?.map((t) => (
              <span key={t} className="tag">{t}</span>
            ))}
          </div>
          {signalId && (
            <Link to={`/signals/${signalId}`} className="detail-link">Full thesis & chart →</Link>
          )}
        </div>
      </div>
    </article>
  );
}

export function bulkMetrics(s: {
  market?: string;
  return_distribution?: Record<string, number | null>;
  calibrated_probability?: number;
  value?: number;
  n_trades?: number;
  historical_win_rate?: number;
}): Metric[] {
  const dist = s.return_distribution || {};
  return [
    { label: "Est. return", value: fmtExp(dist.expected_return_pct as number), accent: true },
    { label: "Confidence", value: fmtPct(s.calibrated_probability) },
    { label: "Deal size", value: fmtValue(s.value, s.market || "IN") },
    { label: "Hold", value: String(dist.sell_horizon_label || "—") },
    { label: "Investor WR", value: fmtPct(s.historical_win_rate) },
    { label: "Trades", value: String(s.n_trades ?? "—") },
  ];
}
