import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiFetch, SignalItem } from "../api";
import { fmtExp, fmtTrackRecord, fmtValue } from "../utils/format";

export default function EntityPage() {
  const { name } = useParams();
  const [data, setData] = useState<{ entity: string; stats: any[]; signals: SignalItem[] } | null>(null);

  useEffect(() => {
    if (!name) return;
    apiFetch(`/entities/${encodeURIComponent(name)}`).then(setData).catch(console.error);
  }, [name]);

  if (!data) return <p>Loading…</p>;

  return (
    <div className="page-stack">
      <section className="card">
        <h2>{data.entity}</h2>
        <p className="muted">
          Track record from realized 3-month returns on past bulk deals.
          {" "}<Link to="/investors">All investors →</Link>
        </p>
        {data.stats.map((s) => (
          <div key={s.market} className="entity-stat-block">
            <h3>{s.market}</h3>
            <div className="metric-row">
              <div className="metric"><span>Track record</span><strong>{fmtTrackRecord(s.win_rate, s.n_trades)}</strong></div>
              <div className="metric"><span>Median return</span><strong>{fmtExp(s.median_return)}</strong></div>
              {s.label && (
                <div className="metric"><span>Typical hold</span><strong>{s.label}</strong></div>
              )}
            </div>
          </div>
        ))}
      </section>
      <section className="card">
        <h3>Deal history</h3>
        <div className="table-wrap">
          <table className="table table-modern">
            <thead><tr><th>Date</th><th>Ticker</th><th>Action</th><th>Deal size</th><th>Tier</th></tr></thead>
            <tbody>
              {data.signals.map((s) => (
                <tr key={s.id}>
                  <td>{new Date(s.disclosed_at).toLocaleDateString()}</td>
                  <td><Link to={`/signals/${s.id}`}>{s.ticker}</Link></td>
                  <td>{s.action}</td>
                  <td>{fmtValue(s.value, s.market)}</td>
                  <td>{s.tier || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
