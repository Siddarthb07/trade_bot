import { Link } from "react-router-dom";
import HoldTimeline, { HoldBanner } from "./HoldTimeline";
import { MiniPriceChart, PricePoint, TrendInfo } from "./PriceChart";
import { fmtExp, fmtPct, fmtValue, tierClass } from "../utils/format";
import { TimeframeInfo } from "../utils/timeframe";

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
  timeframe,
  showTimeline = true,
  prices,
  trend,
  chartLoading,
  onExpand,
  expanded,
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
  timeframe?: TimeframeInfo;
  showTimeline?: boolean;
  prices?: PricePoint[];
  trend?: TrendInfo;
  chartLoading?: boolean;
  onExpand?: () => void;
  expanded?: boolean;
}) {
  return (
    <article className={`stock-panel${expanded ? " is-expanded" : ""}`}>
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

        {timeframe?.hold_days ? <HoldBanner tf={timeframe} compact={!showTimeline} /> : note && <p className="stock-note">{note}</p>}

        {timeframe?.hold_days && showTimeline && <HoldTimeline tf={timeframe} />}

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
          <div className="stock-actions">
            {onExpand && (
              <button type="button" className="btn-link" onClick={onExpand}>
                {expanded ? "Collapse ▲" : "Expand thesis ▼"}
              </button>
            )}
            {signalId && (
              <Link to={`/signals/${signalId}`} className="detail-link">Full page →</Link>
            )}
          </div>
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
    { label: "Hold", value: String(dist.hold_label_short || dist.sell_horizon_label || "—") },
    { label: "Sell by", value: String(dist.exit_date_label || "—") },
    { label: "Deal size", value: fmtValue(s.value, s.market || "IN") },
    { label: "Left", value: String(dist.countdown_label || "—") },
  ];
}
