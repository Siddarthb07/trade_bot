import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, SignalItem } from "../api";

export default function MarketPage() {
  const market = window.location.pathname.endsWith("/us") ? "US" : "IN";
  const [items, setItems] = useState<SignalItem[]>([]);

  useEffect(() => {
    apiFetch<{ items: SignalItem[] }>(`/signals?market=${market}&limit=100`).then((d) => setItems(d.items));
  }, [market]);

  const weekly = items.length;
  const sources = items.reduce<Record<string, number>>((acc, s) => {
    acc[s.source] = (acc[s.source] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="grid">
      <section className="card">
        <h2>{market} Market</h2>
        <p>Recent signals loaded: {weekly}</p>
        <h3>Source breakdown</h3>
        <ul>{Object.entries(sources).map(([k, v]) => <li key={k}>{k}: {v}</li>)}</ul>
      </section>
      <section className="card">
        <h3>Recent signals</h3>
        <ul>
          {items.slice(0, 20).map((s) => (
            <li key={s.id}><Link to={`/signals/${s.id}`}>{s.ticker} · {s.entity} · {s.tier}</Link></li>
          ))}
        </ul>
      </section>
    </div>
  );
}
