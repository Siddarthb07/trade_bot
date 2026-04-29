import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiFetch, SignalItem } from "../api";

export default function EntityPage() {
  const { name } = useParams();
  const [data, setData] = useState<{ entity: string; stats: any[]; signals: SignalItem[] } | null>(null);

  useEffect(() => {
    if (!name) return;
    apiFetch(`/entities/${encodeURIComponent(name)}`).then(setData).catch(console.error);
  }, [name]);

  if (!data) return <p>Loading…</p>;

  return (
    <div className="grid">
      <section className="card">
        <h2>{data.entity}</h2>
        {data.stats.map((s) => (
          <div key={s.market}>
            <h3>{s.market}</h3>
            <p>Win rate: {s.win_rate != null ? `${(s.win_rate * 100).toFixed(1)}%` : "—"}</p>
            <p>Median return: {s.median_return != null ? `${(s.median_return * 100).toFixed(2)}%` : "—"}</p>
            <p>Trades: {s.n_trades}</p>
          </div>
        ))}
      </section>
      <section className="card">
        <h3>Trade Timeline</h3>
        <table className="table">
          <thead><tr><th>Date</th><th>Ticker</th><th>Action</th><th>Tier</th></tr></thead>
          <tbody>
            {data.signals.map((s) => (
              <tr key={s.id}>
                <td>{new Date(s.disclosed_at).toLocaleDateString()}</td>
                <td><Link to={`/signals/${s.id}`}>{s.ticker}</Link></td>
                <td>{s.action}</td>
                <td>{s.tier}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
