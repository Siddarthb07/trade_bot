import { BulkInvestorBacking, BulkPredictionMeta } from "../api";
import { fmtExp, fmtTrackRecord } from "../utils/format";
import DataMaturityBadge from "./DataMaturityBadge";

export default function BulkTrackRecord({
  backing,
  prediction,
}: {
  backing?: BulkInvestorBacking;
  prediction?: BulkPredictionMeta;
}) {
  if (!prediction && !backing?.tracked_past_trades) return null;

  const methodLabel = prediction?.method === "ml" ? "ML-assisted" : "Rule-based";
  const leadWr = fmtTrackRecord(
    prediction?.lead_investor_win_rate,
    prediction?.lead_investor_n_trades,
  );
  const backingWr = backing?.aggregate_win_rate != null && backing.tracked_past_trades
    ? fmtTrackRecord(backing.aggregate_win_rate, backing.tracked_past_trades)
    : null;
  const leadMed = prediction?.lead_investor_median_return;
  const backingMed = backing?.aggregate_median_return;

  return (
    <div className="bulk-track-record">
      <div className="bulk-track-head">
        <strong>Investor track record</strong>
        <span className={`method-badge ${prediction?.method || "rules"}`}>{methodLabel}</span>
      </div>
      <div className="bulk-track-grid">
        <div>
          <span>Lead investor</span>
          <strong>{leadWr}</strong>
          {leadMed != null && <em>Median {fmtExp(leadMed)}</em>}
        </div>
        {backingWr && (
          <div>
            <span>All buyers (avg)</span>
            <strong>{backingWr}</strong>
            {backingMed != null && <em>Median {fmtExp(backingMed)}</em>}
          </div>
        )}
        <div>
          <span>Scorer</span>
          <strong>{prediction?.scorer_version || "interim-v1"}</strong>
        </div>
      </div>
      <p className="muted track-note">
        Past 3-month outcomes after similar bulk buys. Est. return is forward-looking, not guaranteed.
        Model retrains weekly — does not learn from dashboard clicks.
      </p>
      <DataMaturityBadge maturity={prediction?.data_maturity} />
    </div>
  );
}
