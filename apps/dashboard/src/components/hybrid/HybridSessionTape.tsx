import { clsPnL, fmtInr, fmtNum, fmtPct } from "./format";

type Props = {
  runResult: any;
  capital: number;
  lane: string;
  blotterCount: number;
};

export default function HybridSessionTape({ runResult, capital, lane, blotterCount }: Props) {
  const ret = runResult?.return_pct ?? runResult?.compound_pct;
  return (
    <section className="hybrid-northstar tape">
      <div className="ns-card">
        <div className="ns-label">Equity</div>
        <div className="ns-value">{fmtInr(runResult?.capital_end ?? capital, 0)}</div>
        <div className="ns-sub">start {fmtInr(runResult?.capital_start ?? capital, 0)}</div>
      </div>
      <div className="ns-card">
        <div className="ns-label">Session / compound</div>
        <div className={`ns-value ${clsPnL(ret)}`}>{fmtPct(ret)}</div>
        <div className="ns-sub">PnL {fmtInr(runResult?.realized_pnl)}</div>
      </div>
      <div className="ns-card">
        <div className="ns-label">Money deployed</div>
        <div className="ns-value">{fmtInr(runResult?.money_put_total)}</div>
        <div className="ns-sub">returned {fmtInr(runResult?.money_returned_total)}</div>
      </div>
      <div className="ns-card">
        <div className="ns-label">Strategy</div>
        <div className="ns-value ns-sm">{runResult?.strategy_id || "—"}</div>
        <div className="ns-sub">
          {runResult?.regime || "—"} · {lane} · score {fmtNum(runResult?.primary_score, 2)}
        </div>
      </div>
      <div className="ns-card">
        <div className="ns-label">Fills</div>
        <div className="ns-value">{runResult?.n_trades ?? blotterCount}</div>
        <div className="ns-sub">
          eligible {runResult?.eligible_candidates?.length ?? "—"} / rejected{" "}
          {runResult?.rejected_candidates?.length ?? "—"}
        </div>
      </div>
    </section>
  );
}
