import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch } from "../api";
import { fmtExp, fmtValue } from "../utils/format";

interface Position {
  id: string;
  ticker: string;
  market: string;
  status: string;
  qty?: number;
  entry_price?: number;
  entry_date: string;
  exit_price?: number;
  exit_date?: string;
  signal_id?: string;
  notes?: string;
  return_pct?: number;
}

export default function PortfolioPage() {
  const [open, setOpen] = useState<Position[]>([]);
  const [sold, setSold] = useState<Position[]>([]);
  const [tab, setTab] = useState<"open" | "sold">("open");
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ ticker: "", market: "IN", qty: "", entry_price: "", notes: "" });
  const [sellPrices, setSellPrices] = useState<Record<string, string>>({});

  async function load() {
    setLoading(true);
    try {
      const d = await apiFetch<{ open: Position[]; sold: Position[] }>("/portfolio");
      setOpen(d.open);
      setSold(d.sold);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    if (!form.ticker.trim()) return;
    await apiFetch("/portfolio", {
      method: "POST",
      body: JSON.stringify({
        ticker: form.ticker.toUpperCase(),
        market: form.market,
        qty: form.qty ? Number(form.qty) : null,
        entry_price: form.entry_price ? Number(form.entry_price) : null,
        notes: form.notes || null,
      }),
    });
    setForm({ ticker: "", market: "IN", qty: "", entry_price: "", notes: "" });
    load();
  }

  async function markSold(id: string) {
    const price = sellPrices[id] ? Number(sellPrices[id]) : null;
    await apiFetch(`/portfolio/${id}/sell`, {
      method: "PATCH",
      body: JSON.stringify({ exit_price: price }),
    });
    load();
  }

  const rows = tab === "open" ? open : sold;

  return (
    <div className="page-stack">
      <section className="hero-banner">
        <div>
          <span className="eyebrow">Your positions</span>
          <h2>Portfolio — owned & sold</h2>
          <p>
            Track what you bought and sold. Use <strong>I own this</strong> on bulk picks, or add manually below.
            Automated broker execution is planned — see docs/TRADE_AUTOMATION_PLAN.md.
          </p>
        </div>
      </section>

      <div className="tabs">
        <button type="button" className={tab === "open" ? "active" : ""} onClick={() => setTab("open")}>
          Open <span className="count">{open.length}</span>
        </button>
        <button type="button" className={tab === "sold" ? "active" : ""} onClick={() => setTab("sold")}>
          Sold <span className="count">{sold.length}</span>
        </button>
      </div>

      <section className="card">
        <h3>Add position manually</h3>
        <form className="portfolio-form" onSubmit={onAdd}>
          <input placeholder="Ticker" value={form.ticker} onChange={(e) => setForm({ ...form, ticker: e.target.value })} required />
          <select value={form.market} onChange={(e) => setForm({ ...form, market: e.target.value })}>
            <option value="IN">IN</option>
            <option value="US">US</option>
          </select>
          <input placeholder="Qty" value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} />
          <input placeholder="Entry price" value={form.entry_price} onChange={(e) => setForm({ ...form, entry_price: e.target.value })} />
          <input placeholder="Notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          <button type="submit" className="btn-primary">Add open position</button>
        </form>
      </section>

      {loading && <p className="muted">Loading…</p>}

      {!loading && rows.length === 0 && (
        <p className="muted">No {tab} positions. Add from a bulk pick or use the form above.</p>
      )}

      {!loading && rows.length > 0 && (
        <div className="table-wrap">
          <table className="table table-modern">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Entry</th>
                <th>Qty</th>
                <th>Price</th>
                {tab === "sold" && <th>Exit</th>}
                {tab === "sold" && <th>Return</th>}
                {tab === "open" && <th>Mark sold</th>}
                <th>Link</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <td><strong>{p.ticker}</strong> <span className="muted">{p.market}</span></td>
                  <td>{new Date(p.entry_date).toLocaleDateString()}</td>
                  <td>{p.qty ?? "—"}</td>
                  <td>{p.entry_price != null ? fmtValue(p.entry_price, p.market) : "—"}</td>
                  {tab === "sold" && <td>{p.exit_date ? new Date(p.exit_date).toLocaleDateString() : "—"}</td>}
                  {tab === "sold" && <td className={p.return_pct != null && p.return_pct >= 0 ? "ok" : "warn"}>{fmtExp(p.return_pct)}</td>}
                  {tab === "open" && (
                    <td className="sell-cell">
                      <input
                        placeholder="Exit price"
                        value={sellPrices[p.id] || ""}
                        onChange={(e) => setSellPrices({ ...sellPrices, [p.id]: e.target.value })}
                      />
                      <button type="button" className="btn-link" onClick={() => markSold(p.id)}>Sold</button>
                    </td>
                  )}
                  <td>
                    {p.signal_id ? <Link to={`/signals/${p.signal_id}`}>Signal</Link> : "—"}
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
