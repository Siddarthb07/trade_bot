import { useState } from "react";
import { fmtNum } from "./format";

type Props = {
  decisionSummary: any;
  chooser?: any;
  regime?: string;
  strategyId?: string;
};

function WeightBars({ weights }: { weights: Record<string, number> }) {
  const entries = Object.entries(weights || {});
  if (!entries.length) return <p className="muted">No weights</p>;
  const max = Math.max(...entries.map(([, v]) => Number(v) || 0), 0.01);
  return (
    <div className="weight-bars">
      {entries
        .sort((a, b) => Number(b[1]) - Number(a[1]))
        .map(([k, v]) => (
          <div key={k} className="weight-row">
            <span className="weight-label">{k}</span>
            <div className="weight-track">
              <div className="weight-fill" style={{ width: `${(100 * Number(v)) / max}%` }} />
            </div>
            <span className="weight-val">{fmtNum(Number(v), 3)}</span>
          </div>
        ))}
    </div>
  );
}

export default function StrategyDecisionCard({ decisionSummary, chooser, regime, strategyId }: Props) {
  const [open, setOpen] = useState(false);
  const ws = decisionSummary?.why_strategy || {};
  const risk = decisionSummary?.risk || {};
  const weights = ws.weights || chooser?.weights || {};
  const scores = ws.scores || chooser?.scores || {};

  if (!decisionSummary && !chooser && !strategyId) {
    return (
      <section className="hybrid-panel">
        <h3>Why this strategy</h3>
        <p className="muted">Run a day sim to see chooser weights and risk map.</p>
      </section>
    );
  }

  return (
    <section className="hybrid-panel strategy-decision-card">
      <button type="button" className="panel-head pressable" onClick={() => setOpen((o) => !o)}>
        <h3>Why this strategy</h3>
        <span className="muted">{open ? "Hide detail" : "Expand"}</span>
      </button>
      <div className="metric-row">
        <div className="metric accent">
          <span className="label">Picked</span>
          <span className="value">{ws.picked || strategyId || "—"}</span>
        </div>
        <div className="metric">
          <span className="label">Reason</span>
          <span className="value">{ws.reason || chooser?.reason || "—"}</span>
        </div>
        <div className="metric">
          <span className="label">Regime</span>
          <span className="value">{ws.regime || regime || "—"}</span>
        </div>
        <div className="metric">
          <span className="label">Lane</span>
          <span className="value">{ws.lane || "—"}</span>
        </div>
      </div>
      <h4 className="subhead">Chooser weights</h4>
      <WeightBars weights={weights} />
      <h4 className="subhead">Risk map</h4>
      <div className="metric-row">
        {Object.entries(risk).map(([k, v]) => (
          <div key={k} className="metric">
            <span className="label">{k}</span>
            <span className="value">{String(v ?? "—")}</span>
          </div>
        ))}
        {!Object.keys(risk).length && <p className="muted">No risk map on this run.</p>}
      </div>
      {open && (
        <pre className="chooser-debug hybrid-expand-body">
          {JSON.stringify({ why_strategy: ws, scores, chooser, risk }, null, 2)}
        </pre>
      )}
    </section>
  );
}
