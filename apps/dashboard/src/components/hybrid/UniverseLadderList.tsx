import { useState } from "react";
import { fmtNum } from "./format";

type Props = {
  ladder: any[];
  tableView?: boolean;
};

export default function UniverseLadderList({ ladder, tableView }: Props) {
  const [selected, setSelected] = useState<any | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  if (!ladder.length) {
    return (
      <section className="hybrid-panel">
        <h3>Universe ladder</h3>
        <p className="muted">Run a day sim to populate ranked candidates.</p>
      </section>
    );
  }

  if (tableView) {
    return (
      <section className="hybrid-panel">
        <h3>Universe ladder · table</h3>
        <div className="table-scroll tall">
          <table className="bb-table dense">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Ticker</th>
                <th>Elig</th>
                <th>Score</th>
                <th>Conf</th>
                <th>OR bps</th>
                <th>Side</th>
                <th>Reject / reason</th>
              </tr>
            </thead>
            <tbody>
              {ladder.map((r) => (
                <tr
                  key={r.ticker || r.rank}
                  className={r.eligible ? "row-ok" : "row-rej"}
                  onClick={() => setSelected(r)}
                >
                  <td>{r.rank ?? "—"}</td>
                  <td>
                    <strong>{r.ticker}</strong>
                  </td>
                  <td>{r.eligible ? "YES" : "NO"}</td>
                  <td>{fmtNum(r.score, 4)}</td>
                  <td>{fmtNum(r.confidence, 3)}</td>
                  <td>{fmtNum(r.or_width_bps ?? (r.or_width_pct || 0) * 1e4, 1)}</td>
                  <td>{r.side}</td>
                  <td className="wrap">{(r.reject_reasons || []).join(", ") || r.reason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {selected && <pre className="chooser-debug">{JSON.stringify(selected, null, 2)}</pre>}
      </section>
    );
  }

  return (
    <section className="hybrid-panel">
      <h3>Universe ladder · ranked candidates</h3>
      <div className="panel-list hybrid-ladder-list">
        {ladder.map((r) => {
          const id = String(r.ticker || r.rank);
          const open = openId === id;
          return (
            <article
              key={id}
              className={`stock-panel hybrid-ladder-card pressable ${r.eligible ? "elig-yes" : "elig-no"} ${open ? "is-expanded" : ""}`}
              onClick={() => setOpenId(open ? null : id)}
            >
              <div className="stock-body">
                <div className="stock-head">
                  <span className="rank">#{r.rank ?? "—"}</span>
                  <div>
                    <strong>{r.ticker}</strong>
                    <div className="subline">
                      {r.side} · {r.n_bars ?? "—"}@{r.interval || "—"}
                    </div>
                  </div>
                </div>
                <div className="metric-row">
                  <div className="metric">
                    <span className="label">Eligible</span>
                    <span className={`value ${r.eligible ? "pos" : "neg"}`}>{r.eligible ? "YES" : "NO"}</span>
                  </div>
                  <div className="metric accent">
                    <span className="label">Score</span>
                    <span className="value">{fmtNum(r.score, 4)}</span>
                  </div>
                  <div className="metric">
                    <span className="label">Conf</span>
                    <span className="value">{fmtNum(r.confidence, 3)}</span>
                  </div>
                  <div className="metric">
                    <span className="label">OR bps</span>
                    <span className="value">{fmtNum(r.or_width_bps ?? (r.or_width_pct || 0) * 1e4, 1)}</span>
                  </div>
                  <div className="metric">
                    <span className="label">Entry</span>
                    <span className="value">{fmtNum(r.entry_px, 2)}</span>
                  </div>
                </div>
                <div className="tags">
                  <span className={`tag ${r.eligible ? "tag-ok" : "tag-rej"}`}>
                    {r.eligible ? "eligible" : "rejected"}
                  </span>
                  {(r.reject_reasons || []).slice(0, 3).map((x: string) => (
                    <span key={x} className="tag">
                      {x}
                    </span>
                  ))}
                </div>
                {open && (
                  <div className="hybrid-expand-body">
                    <p className="wrap muted">{r.reason || "—"}</p>
                    <pre className="chooser-debug">{JSON.stringify(r, null, 2)}</pre>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
