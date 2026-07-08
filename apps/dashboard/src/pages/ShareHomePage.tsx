import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiFetch, RankedSharePick } from "../api";
import { fmtExp, fmtPct } from "../utils/format";

/** WhatsApp-friendly home link: /h/{token} or /share after /open?k= */
export default function ShareHomePage() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [items, setItems] = useState<RankedSharePick[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (token) sessionStorage.setItem("share_token", token);
  }, [token]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const data = await apiFetch<{ items: RankedSharePick[] }>("/share/ranked-picks?limit=10");
        if (!cancelled) setItems(data.items);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not load picks");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="share-landing">
      <header className="share-landing-header">
        <h1>Trade Bot</h1>
        <p className="muted">Top picks ranked by smart-money backing, then est. return</p>
      </header>

      {loading && <p className="loading-msg">Loading ranked picks…</p>}
      {error && <p className="error-msg">{error}</p>}

      {!loading && !error && items.length === 0 && (
        <section className="card empty-state">
          <h3>No scored picks in the last 14 days</h3>
        </section>
      )}

      {!loading && items.length > 0 && (
        <ol className="share-ranked-list">
          {items.map((pick) => (
            <li key={pick.signal_id} className="share-ranked-item card">
              <div className="share-ranked-head">
                <span className="share-rank">{pick.rank_index}</span>
                <div>
                  <strong>{pick.ticker}</strong>
                  <span className="muted"> · {pick.kind}</span>
                  {pick.theme_name && pick.kind === "Demand" && (
                    <div className="muted share-theme">{pick.theme_name}</div>
                  )}
                </div>
                <span className={`tier-pill tier-${(pick.tier || "low").toLowerCase()}`}>{pick.tier}</span>
              </div>
              <div className="share-ranked-meta">
                <span>Est {fmtExp(pick.expected_return_pct)}</span>
                {pick.calibrated_probability != null && (
                  <span>{fmtPct(pick.calibrated_probability)} conf</span>
                )}
                {pick.hold_label_long && <span>{pick.hold_label_long}</span>}
                {pick.exit_date_label && <span>Sell by {pick.exit_date_label}</span>}
              </div>
              {pick.investor_backing && (
                <p className="muted share-backing">
                  {pick.investor_backing.investor_count} investors · {pick.investor_backing.deal_count} deals
                </p>
              )}
              <Link to={`/signals/${pick.signal_id}`} className="share-pick-link">
                Open pick detail →
              </Link>
              <a href={pick.share_url} className="share-pick-url muted">
                {pick.share_url}
              </a>
            </li>
          ))}
        </ol>
      )}

      <footer className="share-landing-footer">
        <button type="button" className="btn-primary" onClick={() => navigate("/demand")}>
          Open full dashboard
        </button>
        <p className="muted">Same WiFi as PC · Not investment advice</p>
      </footer>
    </div>
  );
}
