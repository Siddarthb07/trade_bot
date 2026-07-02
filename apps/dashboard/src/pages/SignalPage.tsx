import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { DetailPriceChart, TrendInfo } from "../components/PriceChart";
import HoldTimeline, { HoldBanner } from "../components/HoldTimeline";
import { apiFetch, SignalItem } from "../api";
import { fmtPct, fmtValue } from "../utils/format";
import { tfFromDist } from "../utils/timeframe";

interface SignalDetail {
  signal: SignalItem & { calibrated_probability?: number };
  returns: { window: string; return_pct: number | null; price_source: string }[];
  entity_stats: { win_rate: number | null; median_return: number | null; n_trades: number; median_peak_days?: number | null; investor_hold_label?: string | null };
  bulk_investors: {
    entity: string; action: string; value: number | null; qty: number | null;
    disclosed_at: string; source: string;
  }[];
  price_history: { date: string; close: number; volume: number }[];
  thesis: {
    summary: string;
    bull_case: string[];
    risks: string[];
    market_trend: TrendInfo;
    trend_explanation?: { headline: string; paragraphs: string[]; signals: string[] };
    theme?: { headline?: string; paragraphs?: string[]; theme_name?: string; theme_heat?: number; alignment_score?: number };
    disclaimer: string;
  };
  score: Record<string, unknown>;
}

export default function SignalPage() {
  const { id } = useParams();
  const [data, setData] = useState<SignalDetail | null>(null);

  useEffect(() => {
    if (!id) return;
    apiFetch<SignalDetail>(`/signals/${id}`).then(setData).catch(console.error);
  }, [id]);

  if (!data) return <p className="muted">Loading signal…</p>;

  const s = data.signal;
  const prob = s.calibrated_probability ?? (data.score.calibrated_probability as number | undefined);
  const dist = (data.score.return_distribution || {}) as Record<string, unknown>;
  const tf = tfFromDist(dist);
  const isMacro = s.source === "macro_theme";

  return (
    <div className="detail-page">
      <section className="card hold-plan-card">
        <h3>Hold &amp; exit plan</h3>
        {tf.hold_days ? (
          <>
            <HoldBanner tf={tf} />
            <HoldTimeline tf={tf} />
            <p className="muted">Exit window: {String(dist.exit_window_label || "—")} · Tier: {String(dist.timeframe_tier || "—")}</p>
          </>
        ) : (
          <p className="muted">No hold window scored yet — re-run rescore or wait for next ingest.</p>
        )}
      </section>

      <div className="detail-top">
        <section className="card">
          <div className="detail-head">
            <div>
              <h2>{s.ticker} · {s.action}</h2>
              <p className="muted">
                {isMacro ? s.theme?.name || s.entity : s.entity}
                {" · "}{new Date(s.disclosed_at).toLocaleString()}
              </p>
            </div>
            <span className={`tier ${s.tier?.toLowerCase()}`}>{s.tier}</span>
          </div>
          <p className="thesis-summary">{data.thesis.summary}</p>
          <div className="detail-kpis">
            <div><span>Confidence</span><strong>{prob != null ? `${(prob * 100).toFixed(0)}%` : "—"}</strong></div>
            <div><span>Est. return</span><strong className="ok">{dist.expected_return_pct != null ? `+${((dist.expected_return_pct as number) * 100).toFixed(0)}%` : "—"}</strong></div>
            <div><span>Hold</span><strong>{String(dist.hold_label_long || dist.sell_horizon_label || "—")}</strong></div>
            <div><span>Sell by</span><strong>{String(dist.exit_date_full || dist.exit_date_label || "—")}</strong></div>
            <div><span>Review</span><strong>{String(dist.review_date_label || "—")}</strong></div>
            {!isMacro && <div><span>Deal</span><strong>{fmtValue(s.value, s.market)}</strong></div>}
            {isMacro && s.theme?.theme_heat != null && (
              <div><span>Theme heat</span><strong>{Math.round(s.theme.theme_heat * 100)}%</strong></div>
            )}
          </div>
        </section>

        <section className="card chart-card">
          <h3>Price — 6 months</h3>
          <DetailPriceChart prices={data.price_history} trend={data.thesis.market_trend} height={320} />
        </section>
      </div>

      {data.thesis.theme && (
        <section className="card">
          <h3>{data.thesis.theme.headline || "Theme context"}</h3>
          {data.thesis.theme.paragraphs?.map((p, i) => <p key={i} className="body-text">{p}</p>)}
        </section>
      )}

      {data.thesis.trend_explanation && (
        <section className="card">
          <h3>{data.thesis.trend_explanation.headline}</h3>
          {data.thesis.trend_explanation.paragraphs.map((p, i) => <p key={i} className="body-text">{p}</p>)}
          <ul className="bullet-list">{data.thesis.trend_explanation.signals.map((x, i) => <li key={i}>{x}</li>)}</ul>
        </section>
      )}

      <div className="grid-2">
        <section className="card">
          <h3>Why it might work</h3>
          <ul className="bullet-list ok">{data.thesis.bull_case.map((b, i) => <li key={i}>{b}</li>)}</ul>
          {data.thesis.risks.length > 0 && (
            <>
              <h4>Risks</h4>
              <ul className="bullet-list warn">{data.thesis.risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
            </>
          )}
        </section>

        <section className="card">
          <h3>Forward returns</h3>
          <table className="table">
            <thead><tr><th>Window</th><th>Return</th></tr></thead>
            <tbody>
              {data.returns.map((r) => (
                <tr key={r.window}>
                  <td>{r.window}</td>
                  <td>{r.return_pct != null ? `${(r.return_pct * 100).toFixed(2)}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
      {!isMacro && (
            <p className="muted">
              Investor: WR {fmtPct(data.entity_stats.win_rate, 1)} · median {fmtPct(data.entity_stats.median_return, 1)} · n={data.entity_stats.n_trades}
              {data.entity_stats.investor_hold_label && (
                <> · {data.entity_stats.investor_hold_label}</>
              )}
            </p>
          )}
        </section>
      </div>

      {!isMacro && data.bulk_investors.length > 0 && (
        <section className="card">
          <h3>Bulk investors on {s.ticker}</h3>
          <table className="table">
            <thead><tr><th>Date</th><th>Investor</th><th>Action</th><th>Value</th></tr></thead>
            <tbody>
              {data.bulk_investors.map((b, i) => (
                <tr key={i}>
                  <td>{new Date(b.disclosed_at).toLocaleDateString()}</td>
                  <td><Link to={`/entities/${encodeURIComponent(b.entity)}`}>{b.entity}</Link></td>
                  <td>{b.action}</td>
                  <td>{fmtValue(b.value, s.market)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {(dist.partial_exit_plan as { day: number; action: string; note: string }[] | undefined)?.length ? (
        <section className="card">
          <h3>Staged exit plan</h3>
          <ul className="exit-stages">
            {(dist.partial_exit_plan as { day: number; action: string; note: string }[]).map((s) => (
              <li key={s.day}>
                <strong>Day {s.day}</strong> — {s.action}
                <span>{s.note}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className="disclaimer">{data.thesis.disclaimer}</p>
    </div>
  );
}
