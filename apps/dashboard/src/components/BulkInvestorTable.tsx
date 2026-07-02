import { Link } from "react-router-dom";
import { fmtExp, fmtTrackRecord, fmtValue } from "../utils/format";

export interface BulkInvestorRow {
  entity: string;
  total_value: number;
  deal_count?: number;
  latest_at?: string;
  action?: string;
  qty?: number | null;
  implied_price?: number;
  source?: string;
  win_rate?: number | null;
  median_return?: number | null;
  n_trades?: number;
}

export interface BulkInvestorBacking {
  investors: BulkInvestorRow[];
  total_value: number;
  investor_count: number;
  deal_count: number;
  window_days: number;
  aggregate_win_rate?: number | null;
  aggregate_median_return?: number | null;
  tracked_past_trades?: number;
}

export default function BulkInvestorTable({
  backing,
  market,
  compact,
}: {
  backing: BulkInvestorBacking;
  market: string;
  compact?: boolean;
}) {
  if (!backing.investors.length) return null;

  return (
    <div className={`bulk-backing${compact ? " compact" : ""}`}>
      <div className="bulk-backing-head">
        <strong>Smart-money backing</strong>
        <span className="muted">last {backing.window_days} days</span>
      </div>
      <div className="bulk-backing-total">
        <span>Total {fmtValue(backing.total_value, market)}</span>
        <span>{backing.investor_count} investor{backing.investor_count === 1 ? "" : "s"}</span>
        <span>{backing.deal_count} deal{backing.deal_count === 1 ? "" : "s"}</span>
        {backing.aggregate_win_rate != null && backing.tracked_past_trades ? (
          <span>Avg win {fmtTrackRecord(backing.aggregate_win_rate, backing.tracked_past_trades)}</span>
        ) : null}
      </div>
      <div className="table-wrap">
        <table className="table table-compact bulk-investor-table">
          <thead>
            <tr>
              <th>Investor</th>
              <th>Amount</th>
              <th>Track record</th>
              {!compact && <th>Deals</th>}
              <th>Last buy</th>
            </tr>
          </thead>
          <tbody>
            {backing.investors.map((inv) => (
              <tr key={inv.entity}>
                <td>
                  <Link to={`/entities/${encodeURIComponent(inv.entity)}`} title={inv.entity}>
                    {inv.entity.length > (compact ? 32 : 48) ? `${inv.entity.slice(0, compact ? 29 : 45)}…` : inv.entity}
                  </Link>
                </td>
                <td><strong>{fmtValue(inv.total_value, market)}</strong></td>
                <td>
                  {fmtTrackRecord(inv.win_rate, inv.n_trades)}
                  {inv.median_return != null && inv.n_trades ? (
                    <span className="muted"> · med {fmtExp(inv.median_return)}</span>
                  ) : null}
                </td>
                {!compact && <td>{inv.deal_count ?? 1}</td>}
                <td>{inv.latest_at ? new Date(inv.latest_at).toLocaleDateString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
