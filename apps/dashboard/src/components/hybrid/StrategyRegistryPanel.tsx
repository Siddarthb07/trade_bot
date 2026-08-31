import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { clsPnL, fmtNum, fmtPct } from "./format";

type StrategyMeta = {
  id: string;
  family?: string;
  description?: string;
  lanes?: string[];
  sim_ready?: boolean;
};

type Props = {
  strategies: StrategyMeta[];
  chooserState: any;
  learningCurve: any[];
  daily?: any[];
};

const tipStyle = {
  background: "#0f1524",
  border: "1px solid #2a3550",
  borderRadius: 8,
  fontSize: 12,
};

export function EquitySpark({ daily }: { daily: any[] }) {
  if (!daily?.length) return null;
  const data = daily
    .filter((d) => d.capital_end != null)
    .map((d) => ({ date: d.asof, equity: Number(d.capital_end), ret: Number(d.return_pct || 0) }));
  if (!data.length) return null;
  return (
    <section className="hybrid-panel">
      <h3>Window equity</h3>
      <div style={{ height: 180 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="eqFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#4f7cff" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#4f7cff" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="#1a2336" strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fill: "#8b9bb8", fontSize: 10 }} />
            <YAxis tick={{ fill: "#8b9bb8", fontSize: 10 }} domain={["auto", "auto"]} width={56} />
            <Tooltip contentStyle={tipStyle} />
            <Area type="monotone" dataKey="equity" stroke="#4f7cff" fill="url(#eqFill)" strokeWidth={2} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

export default function StrategyRegistryPanel({ strategies, chooserState, learningCurve, daily }: Props) {
  const per = chooserState?.strategies || {};
  const expectData = Object.entries(per).map(([id, st]: any) => ({
    id,
    expectancy: Number(st.expectancy || 0),
    n: Number(st.n || 0),
    hit: Number(st.hit_rate || 0) * 100,
  }));

  return (
    <div className="strategies-stack">
      {daily && daily.length > 0 && <EquitySpark daily={daily} />}

      <section className="hybrid-panel">
        <h3>Strategy registry</h3>
        <div className="panel-list">
          {(strategies.length ? strategies : Object.keys(per).map((id) => ({ id }))).map((s) => {
            const st = per[s.id] || {};
            return (
              <article key={s.id} className="stock-panel hybrid-strat-card">
                <div className="stock-body">
                  <div className="stock-head">
                    <strong>{s.id}</strong>
                    <div className="subline">{s.description || s.family || "—"}</div>
                  </div>
                  <div className="metric-row">
                    <div className="metric accent">
                      <span className="label">Expectancy</span>
                      <span className={`value ${clsPnL(st.expectancy)}`}>{fmtNum(st.expectancy, 4)}</span>
                    </div>
                    <div className="metric">
                      <span className="label">n</span>
                      <span className="value">{st.n ?? 0}</span>
                    </div>
                    <div className="metric">
                      <span className="label">Hit</span>
                      <span className="value">{st.hit_rate != null ? fmtPct(Number(st.hit_rate) * 100, 0) : "—"}</span>
                    </div>
                    <div className="metric">
                      <span className="label">Sim ready</span>
                      <span className="value">{s.sim_ready === false ? "no" : s.sim_ready ? "yes" : "—"}</span>
                    </div>
                  </div>
                  <div className="tags">
                    {(s.lanes || []).map((l: string) => (
                      <span key={l} className={`tag lane-badge lane-${l}`}>
                        {l}
                      </span>
                    ))}
                  </div>
                </div>
              </article>
            );
          })}
          {!strategies.length && !Object.keys(per).length && (
            <p className="muted">No strategies loaded — check API `/exec/hybrid/strategies`.</p>
          )}
        </div>
      </section>

      {expectData.length > 0 && (
        <section className="hybrid-panel">
          <h3>Expectancy by strategy</h3>
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={expectData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#1a2336" strokeDasharray="3 3" />
                <XAxis dataKey="id" tick={{ fill: "#8b9bb8", fontSize: 11 }} />
                <YAxis tick={{ fill: "#8b9bb8", fontSize: 10 }} width={48} />
                <Tooltip contentStyle={tipStyle} />
                <Bar dataKey="expectancy" fill="#4f7cff" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      {learningCurve?.length > 0 && (
        <section className="hybrid-panel">
          <h3>Learning curve (recent outcomes)</h3>
          <div className="table-scroll">
            <table className="bb-table dense">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Asof</th>
                  <th>Strategy</th>
                  <th>PnL%</th>
                  <th>Lane</th>
                </tr>
              </thead>
              <tbody>
                {learningCurve.slice(-30).map((r: any) => (
                  <tr key={r.i}>
                    <td>{r.i}</td>
                    <td>{r.asof}</td>
                    <td>{r.strategy_id}</td>
                    <td className={clsPnL(r.pnl_pct)}>{r.pnl_pct}</td>
                    <td>{r.lane}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
