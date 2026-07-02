import { Link } from "react-router-dom";
import { useState } from "react";
import { apiFetch, BulkInvestorBacking, BulkPredictionMeta } from "../api";
import { fmtValue } from "../utils/format";
import BulkInvestorTable from "./BulkInvestorTable";
import BulkTrackRecord from "./BulkTrackRecord";
import StockPanel, { Metric } from "./StockPanel";
import { PricePoint, TrendInfo } from "./PriceChart";
import { TimeframeInfo } from "../utils/timeframe";

interface Brief {
  summary?: string;
  bull_case?: string[];
  risks?: string[];
  bulk_investors?: { entity: string; action: string; value: number | null; disclosed_at: string }[];
  partial_exit_plan?: { day: number; action: string; note: string }[];
  investor_hold_label?: string;
}

export default function ExpandableStockPanel({
  signalId,
  market,
  compareMode,
  compareSelected,
  onCompareToggle,
  investorBacking,
  prediction,
  ...panel
}: {
  signalId?: string | null;
  market: string;
  compareMode?: boolean;
  compareSelected?: boolean;
  onCompareToggle?: (id: string, selected: boolean) => void;
  rank?: number;
  ticker: string;
  headline: string;
  subline?: string;
  tier?: string;
  metrics: Metric[];
  tags?: string[];
  timeframe?: TimeframeInfo;
  showTimeline?: boolean;
  investorBacking?: BulkInvestorBacking;
  prediction?: BulkPredictionMeta;
  prices?: PricePoint[];
  trend?: TrendInfo;
  chartLoading?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [brief, setBrief] = useState<Brief | null>(null);
  const [loadingBrief, setLoadingBrief] = useState(false);
  const [portfolioMsg, setPortfolioMsg] = useState("");

  async function addToPortfolio() {
    if (!signalId) return;
    setPortfolioMsg("Saving…");
    try {
      await apiFetch(`/portfolio/from-signal/${signalId}`, { method: "POST", body: "{}" });
      setPortfolioMsg("Added to portfolio →");
    } catch {
      setPortfolioMsg("Could not save");
    }
  }

  async function toggle() {
    if (!signalId) return;
    const next = !open;
    setOpen(next);
    if (next && !brief && signalId) {
      setLoadingBrief(true);
      try {
        const data = await apiFetch<Brief>(`/signals/${signalId}/brief`);
        setBrief(data);
      } catch {
        setBrief({ summary: "Could not load thesis." });
      } finally {
        setLoadingBrief(false);
      }
    }
  }

  return (
    <div className={`expand-panel${open ? " expanded" : ""}`}>
      {compareMode && signalId && (
        <label className="compare-check">
          <input
            type="checkbox"
            checked={!!compareSelected}
            onChange={(e) => onCompareToggle?.(signalId, e.target.checked)}
          />
          Compare
        </label>
      )}
      <StockPanel
        {...panel}
        signalId={signalId}
        market={market}
        onExpand={signalId ? toggle : undefined}
        expanded={open}
      />
      {signalId && (
        <div className="portfolio-actions">
          <button type="button" className="btn-link" onClick={addToPortfolio}>I own this</button>
          <Link to="/portfolio" className="btn-link">My portfolio</Link>
          {portfolioMsg && <span className="muted">{portfolioMsg}</span>}
        </div>
      )}
      {investorBacking && investorBacking.investors.length > 0 && (
        <>
          <BulkTrackRecord backing={investorBacking} prediction={prediction} />
          <BulkInvestorTable backing={investorBacking} market={market} compact />
        </>
      )}
      {open && signalId && (
        <div className="expand-body">
          {loadingBrief && <p className="muted">Loading thesis…</p>}
          {!loadingBrief && brief && (
            <>
              {brief.summary && <p className="body-text">{brief.summary}</p>}
              {brief.investor_hold_label && (
                <p className="muted investor-hold-note">{brief.investor_hold_label}</p>
              )}
              {brief.bull_case && brief.bull_case.length > 0 && (
                <ul className="bullet-list ok">
                  {brief.bull_case.map((b, i) => <li key={i}>{b}</li>)}
                </ul>
              )}
              {brief.risks && brief.risks.length > 0 && (
                <ul className="bullet-list warn">
                  {brief.risks.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              )}
              {brief.bulk_investors && brief.bulk_investors.length > 0 && (
                <table className="table table-compact">
                  <thead>
                    <tr><th>Date</th><th>Investor</th><th>Value</th></tr>
                  </thead>
                  <tbody>
                    {brief.bulk_investors.map((b, i) => (
                      <tr key={i}>
                        <td>{new Date(b.disclosed_at).toLocaleDateString()}</td>
                        <td>{b.entity}</td>
                        <td>{fmtValue(b.value, market)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {brief.partial_exit_plan && brief.partial_exit_plan.length > 0 && (
                <div className="partial-exit">
                  <h4>Staged exit plan</h4>
                  <ul className="exit-stages">
                    {brief.partial_exit_plan.map((s) => (
                      <li key={s.day}>
                        <strong>Day {s.day}</strong> — {s.action}
                        <span>{s.note}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
