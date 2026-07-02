import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { fmtExp, fmtTrackRecord } from "../utils/format";

interface InvestorRow {
  entity: string;
  entity_normalized: string;
  market: string;
  win_rate: number | null;
  median_return: number | null;
  n_trades: number;
  recent_deals: { ticker: string; value: number | null; disclosed_at: string; signal_id: string }[];
}

export default function InvestorsPage() {
  const [items, setItems] = useState<InvestorRow[]>([]);
  const [market, setMarket] = useState("IN");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    apiFetch<{ items: InvestorRow[] }>(`/investors?market=${market}&min_trades=1&limit=60`)
      .then((d) => setItems(d.items))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [market]);

  return (
    <div className="page-stack">
      <section className="hero-banner">
        <div>
          <span className="eyebrow">NSE bulk smart money</span>
          <h2>Investor track record</h2>
          <p>
            Win rates from realized 3-month returns after past bulk buys.
            Not self-learning — recomputed when forward returns mature.
          </p>
        </div>
      </section>

      <div className="toolbar toolbar-card">
        <select value={market} onChange={(e) => setMarket(e.target.value)}>
          <option value="IN">India</option>
          <option value="US">US</option>
        </select>
      </div>

      {loading && <p className="muted">Loading…</p>}

      {!loading && (
        <div className="table-wrap">
          <table className="table table-modern">
            <thead>
              <tr>
                <th>#</th>
                <th>Investor</th>
                <th>Track record</th>
                <th>Median ret.</th>
                <th>Recent buys</th>
              </tr>
            </thead>
            <tbody>
              {items.map((inv, i) => (
                <tr key={inv.entity_normalized}>
                  <td>{i + 1}</td>
                  <td>
                    <Link to={`/entities/${encodeURIComponent(inv.entity)}`}>{inv.entity}</Link>
                  </td>
                  <td>{fmtTrackRecord(inv.win_rate, inv.n_trades)}</td>
                  <td>{fmtExp(inv.median_return)}</td>
                  <td className="recent-deals">
                    {inv.recent_deals.slice(0, 3).map((d) => (
                      <Link key={d.signal_id} to={`/signals/${d.signal_id}`} className="tag">
                        {d.ticker}
                      </Link>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
