import HoldTimeline, { HoldBanner } from "./HoldTimeline";
import { MiniPriceChart, PricePoint, TrendInfo } from "./PriceChart";
import { TimeframeInfo } from "../utils/timeframe";
import { fmtExp, fmtPct } from "../utils/format";

export interface CompareItem {
  id: string;
  ticker: string;
  market: string;
  tier?: string;
  expected?: number;
  prob?: number;
  tf?: TimeframeInfo;
  prices?: PricePoint[];
  trend?: TrendInfo;
}

export default function CompareTray({
  items,
  onClear,
}: {
  items: CompareItem[];
  onClear: () => void;
}) {
  if (items.length === 0) return null;

  return (
    <div className="compare-tray">
      <div className="compare-tray-head">
        <strong>Compare ({items.length}/3)</strong>
        <button type="button" className="btn-link" onClick={onClear}>Clear</button>
      </div>
      <div className="compare-grid">
        {items.map((item) => (
          <div key={item.id} className="compare-col">
            <h4>{item.ticker} <span className="muted">{item.market}</span></h4>
            <MiniPriceChart prices={item.prices || []} trend={item.trend} height={80} />
            <div className="compare-metrics">
              <span>Est. {fmtExp(item.expected)}</span>
              <span>{fmtPct(item.prob)} conf</span>
              <span>{item.tier}</span>
            </div>
            {item.tf?.hold_days && (
              <>
                <HoldBanner tf={item.tf} compact />
                <HoldTimeline tf={item.tf} compact />
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
