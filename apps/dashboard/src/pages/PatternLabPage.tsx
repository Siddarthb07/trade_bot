import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiFetch } from "../api";
import { DetailPriceChart, type PricePoint, type TradeMarker } from "../components/PriceChart";

type Summary = {
  best_label?: string;
  best_green_months?: number;
  best_return_pct?: number;
  goal_met?: boolean;
  lane?: string;
  total_return_pct?: number;
  green_months?: number;
  months_total?: number;
  worst_month_pct?: number;
  worst_month_pnl?: number;
  year_pnl?: number;
  loss_lte_profits?: boolean;
  capital_end?: number;
  capital_start?: number;
  claim?: string;
  promoted?: string;
};

type MonthRow = {
  month: string;
  label?: string;
  pnl: number;
  n_trades: number;
  wins?: number;
  month_return_pct?: number;
  capital_end?: number;
};

type StrategyCard = {
  role?: string;
  lane: string;
  run_id?: string;
  capital_start?: number;
  capital_end: number;
  year_pnl: number;
  total_return_pct: number;
  green_months?: number;
  months_total?: number;
  worst_month_pct?: number;
  worst_month_pnl?: number | null;
  loss_lte_profits?: boolean;
  months?: MonthRow[];
  knobs?: Record<string, unknown>;
  n_trades?: number;
};

type StretchPanel = {
  variant?: string;
  lane?: string;
  claim?: string;
  nine_nine?: boolean;
  locked_v2_untouched?: boolean;
  summary?: {
    years_positive?: number;
    sum_pnl?: number;
    y2020?: number;
    y2021?: number;
  };
  years?: { year: number; label?: string; return_pct: number; worst_month_pct?: number; n_trades?: number }[];
  chart?: ChartRow[];
};

type ChartRow = { name: string; end: number; pnl: number; ret: number; fill?: string };

type AgentMsg = {
  agent?: string;
  vote?: string;
  reason?: string;
  weight?: number;
  status?: string;
  payload?: Record<string, unknown>;
};

type Decision = {
  ts?: string;
  asof?: string;
  ticker?: string;
  family?: string;
  choice?: string;
  skip_reason?: string;
  primary?: {
    side?: string;
    reason?: string;
    confidence?: number;
    hybrid_choice?: { picked?: string; regime?: string; reason?: string; scores?: Record<string, number> };
  };
  hybrid_choice?: { picked?: string; regime?: string; reason?: string; scores?: Record<string, number> };
  swarm_agreement?: {
    score?: number;
    tradeable?: boolean;
    reason?: string;
    tau?: number;
    collapsed_votes?: number;
    raw_skip_votes?: number;
    hard_skip_agents?: string[];
  };
  swarm_messages?: AgentMsg[];
  feed_status?: Record<string, string>;
};

type Trade = {
  ts?: string;
  asof?: string;
  ticker?: string;
  side?: string;
  pnl?: number;
  pnl_pct?: number;
  exit_reason?: string;
  family?: string;
  entry_price?: number;
  exit_price?: number;
  exit_asof?: string;
  signal_reason?: string;
  leverage?: number;
};

type EquityCompareRow = { month: string; v2?: number | null; v2_1?: number | null; v3?: number | null };

type ChartPayload = {
  ticker: string;
  asof: string;
  prices: PricePoint[];
  markers: TradeMarker[];
  entry_price?: number | null;
  exit_price?: number | null;
  side?: string | null;
};

type Mistake = {
  ts?: string;
  asof?: string;
  mistake_type?: string;
  ticker?: string;
  lesson?: string;
};

type MistakeBriefing = {
  summary?: string;
  exclude_tickers?: string[];
  sitout?: boolean;
  size_mult?: number;
};

type Iteration = {
  ts?: string;
  label?: string;
  family?: string;
  green_months?: number;
  total_return_pct?: number;
  keep?: boolean;
  goal_met?: boolean;
  run_id?: string;
  lane?: string;
  worst_month_pct?: number;
  year_pnl?: number;
  capital_end?: number;
  loss_lte_profits?: boolean;
  knobs?: Record<string, unknown>;
  months_total?: number;
};

type RunRow = Iteration & { kind?: string };
type TabId = "overview" | "swarm" | "ledger";

const STUB_AGENTS = new Set([
  "VPIN",
  "Hawkes",
  "Kyle",
  "PeerRank#1",
  "PeerRank#2",
  "PeerRank#3",
  "PeerRank#4",
  "PeerRank#5",
]);

const AGENT_ORDER = [
  "RulesClerk",
  "Regime",
  "BreadthRegime",
  "DailySwingChooser",
  "CrossMarketOpen",
  "CrossSectionSimilarity",
  "ProfitGuard",
  "Cost",
  "NoRuin",
];

function monthLabel(m: MonthRow | { month: string; label?: string }) {
  if (m.label) return m.label;
  const raw = String(m.month || "");
  if (/^\d{4}-\d{2}/.test(raw)) return raw.slice(5, 7);
  const map: Record<string, string> = {
    january: "Jan",
    february: "Feb",
    march: "Mar",
    april: "Apr",
    may: "May",
    june: "Jun",
    july: "Jul",
    august: "Aug",
    september: "Sep",
    october: "Oct",
    november: "Nov",
    december: "Dec",
  };
  return map[raw.toLowerCase()] || raw.slice(0, 3);
}

function fmtPct(n: number | undefined | null) {
  if (n === undefined || n === null || Number.isNaN(n)) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function fmtInr(n: number | undefined | null) {
  if (n === undefined || n === null) return "—";
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

function voteClass(v?: string) {
  if (v === "take") return "pl-vote-pill take";
  if (v === "skip") return "pl-vote-pill skip";
  return "pl-vote-pill annotate";
}

function voteGlyph(v?: string) {
  if (v === "take") return "T";
  if (v === "skip") return "S";
  return "·";
}

function isStub(m: AgentMsg) {
  if (STUB_AGENTS.has(String(m.agent || ""))) return true;
  const st = String(m.status || "");
  return st === "insufficient_data" || st === "missing" || st === "cold_start";
}

const tipStyle = { background: "#16181d", border: "1px solid #2a2e36", borderRadius: 8 };

export default function PatternLabPage() {
  const [tab, setTab] = useState<TabId>("overview");
  const [summary, setSummary] = useState<Summary>({});
  const [months, setMonths] = useState<MonthRow[]>([]);
  const [strategies, setStrategies] = useState<StrategyCard[]>([]);
  const [chartRows, setChartRows] = useState<ChartRow[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [iterations, setIterations] = useState<Iteration[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [mistakes, setMistakes] = useState<Mistake[]>([]);
  const [briefing, setBriefing] = useState<MistakeBriefing | null>(null);
  const [selected, setSelected] = useState<Decision | null>(null);
  const [selectedIter, setSelectedIter] = useState<Iteration | StrategyCard | null>(null);
  const [agentFilter, setAgentFilter] = useState<"all" | "take" | "skip" | "annotate">("all");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [equityCompare, setEquityCompare] = useState<EquityCompareRow[]>([]);
  const [priceChart, setPriceChart] = useState<ChartPayload | null>(null);
  const [chartBusy, setChartBusy] = useState(false);
  const [disclaimer, setDisclaimer] = useState("");
  const [stretchPanel, setStretchPanel] = useState<StretchPanel | null>(null);

  const loadChart = useCallback(async (ticker?: string, asof?: string) => {
    if (!ticker || !asof || ticker === "cash") {
      setPriceChart(null);
      return;
    }
    setChartBusy(true);
    try {
      const q = new URLSearchParams({ ticker, asof: asof.slice(0, 10), lookback: "60" });
      setPriceChart(await apiFetch<ChartPayload>(`/exec/pattern-forge/chart?${q}`));
    } catch {
      setPriceChart(null);
    } finally {
      setChartBusy(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [s, d, t, it, mist] = await Promise.all([
        apiFetch<{
          summary: Summary;
          months_2025: MonthRow[];
          strategies?: StrategyCard[];
          chart?: ChartRow[];
          equity_compare?: EquityCompareRow[];
          disclaimer?: string;
          stretch_panel?: StretchPanel | null;
        }>("/exec/pattern-forge/summary"),
        apiFetch<{ decisions: Decision[] }>("/exec/pattern-forge/decisions?limit=300"),
        apiFetch<{ trades: Trade[] }>("/exec/pattern-forge/trades?limit=200"),
        apiFetch<{ iterations: Iteration[]; runs: RunRow[] }>("/exec/pattern-forge/iterations?limit=40"),
        apiFetch<{ mistakes: Mistake[]; briefing: MistakeBriefing }>("/exec/pattern-forge/mistakes?limit=60"),
      ]);
      setSummary(s.summary || {});
      setMonths(s.months_2025 || []);
      setStrategies(s.strategies || []);
      setChartRows(s.chart || []);
      setEquityCompare(s.equity_compare || []);
      setDisclaimer(s.disclaimer || "");
      setStretchPanel(s.stretch_panel || null);
      const decs = d.decisions || [];
      setDecisions(decs);
      setTrades(t.trades || []);
      setIterations(it.iterations || []);
      setRuns(it.runs || []);
      setMistakes(mist.mistakes || []);
      setBriefing(mist.briefing || null);
      setSelected((prev) => {
        if (!prev) return decs.find((x) => (x.swarm_messages || []).length > 0) || decs[0] || null;
        return decs.find((x) => x.ts === prev.ts && x.asof === prev.asof && x.ticker === prev.ticker) || prev;
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 20000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (selected?.ticker && selected?.asof && selected.ticker !== "cash") {
      void loadChart(selected.ticker, selected.asof);
    }
  }, [selected?.ticker, selected?.asof, loadChart]);

  const green = summary.best_green_months ?? summary.green_months ?? 0;
  const heroLane = summary.promoted || summary.lane || summary.best_label || "v2";

  const dayAgents = useMemo(() => {
    const list = selected?.swarm_messages || [];
    if (agentFilter === "all") return list;
    return list.filter((m) => (m.vote || "annotate") === agentFilter);
  }, [selected, agentFilter]);

  const voteCounts = useMemo(() => {
    const list = selected?.swarm_messages || [];
    return {
      take: list.filter((m) => m.vote === "take").length,
      skip: list.filter((m) => m.vote === "skip").length,
      annotate: list.filter((m) => m.vote !== "take" && m.vote !== "skip").length,
      n: list.length,
    };
  }, [selected]);

  const matrix = useMemo(() => {
    const withSwarm = decisions.filter((d) => (d.swarm_messages || []).length > 0).slice(0, 14);
    const seen = new Set<string>();
    const found: string[] = [];
    for (const d of withSwarm) {
      for (const m of d.swarm_messages || []) {
        const a = String(m.agent || "?");
        if (!seen.has(a) && !a.startsWith("PeerRank")) {
          seen.add(a);
          found.push(a);
        }
      }
    }
    const ordered = [...AGENT_ORDER.filter((a) => found.includes(a)), ...found.filter((a) => !AGENT_ORDER.includes(a))];
    return {
      days: withSwarm,
      rows: ordered.map((agent) => ({
        agent,
        cells: withSwarm.map((d) => {
          const msg = (d.swarm_messages || []).find((m) => m.agent === agent);
          return { vote: msg?.vote || "annotate", reason: msg?.reason || "", stub: msg ? isStub(msg) : true };
        }),
      })),
    };
  }, [decisions]);

  const iterList = useMemo(
    () => [...iterations, ...runs.map((r) => ({ ...r, label: r.label || r.lane || r.family || r.run_id }))],
    [iterations, runs]
  );

  const selectDecision = (d: Decision) => {
    setSelected(d);
    setTab("swarm");
  };

  return (
    <div className="pattern-lab">
      <header className="pl-hero">
        <div className="pl-hero-copy">
          <p className="pl-eyebrow">Pattern Lab</p>
          <h1>Forge desk</h1>
          <p className="pl-sub">
            Locked hero <span className="pl-badge">{heroLane}</span>
            {" · "}clean-PIT daily swing · paper/sim only
          </p>
        </div>
        <div className="pl-hero-actions">
          <button type="button" className="pl-btn" onClick={() => void refresh()} disabled={busy}>
            {busy ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      {error && <p className="pl-error">{error}</p>}

      <nav className="pl-tabs" aria-label="Pattern Lab sections">
        {(
          [
            ["overview", "Overview"],
            ["swarm", "Swarm"],
            ["ledger", "Ledger"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`pl-tab ${tab === id ? "active" : ""}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab === "overview" && (
        <>
          <section className="pl-glass pl-metrics" aria-label="Hero metrics">
            <div className="pl-metric">
              <span className="pl-metric-label">End capital</span>
              <strong className={(summary.capital_end ?? 0) >= (summary.capital_start ?? 10000) ? "up" : "down"}>
                {fmtInr(summary.capital_end)}
              </strong>
              <span className="pl-soft">from {fmtInr(summary.capital_start ?? 10000)}</span>
            </div>
            <div className="pl-metric">
              <span className="pl-metric-label">Year return</span>
              <strong className={(summary.best_return_pct ?? summary.total_return_pct ?? 0) >= 0 ? "up" : "down"}>
                {fmtPct(summary.best_return_pct ?? summary.total_return_pct)}
              </strong>
              <span className="pl-soft">{fmtInr(summary.year_pnl)} pnl</span>
            </div>
            <div className="pl-metric">
              <span className="pl-metric-label">Worst month</span>
              <strong className={(summary.worst_month_pct ?? 0) > -12 ? "up" : "down"}>
                {fmtPct(summary.worst_month_pct)}
              </strong>
              <span className="pl-soft">{fmtInr(summary.worst_month_pnl)}</span>
            </div>
            <div className="pl-metric">
              <span className="pl-metric-label">Loss ≤ profits</span>
              <strong className={summary.loss_lte_profits ? "up" : "down"}>
                {summary.loss_lte_profits ? "Yes" : "No"}
              </strong>
              <span className="pl-soft">
                {green}/{summary.months_total ?? 12} green
              </span>
            </div>
          </section>

          {stretchPanel && (stretchPanel.chart || []).length > 0 && (
            <section className="pl-glass pl-panel pl-stretch-panel" aria-label="Stretch survivor">
              <div className="pl-panel-head">
                <h2>
                  Stretch survivor · <span className="pl-badge pl-badge-stretch">{stretchPanel.variant || "guard_omega_d"}</span>
                </h2>
                <p className="pl-soft">
                  {stretchPanel.summary?.years_positive ?? stretchPanel.years?.length ?? 0}/9 positive standalone years · ₹10k/yr · stretch lane · not live
                </p>
              </div>
              <div className="pl-stretch-stats">
                <div className="pl-metric">
                  <span className="pl-metric-label">Sum PnL</span>
                  <strong className="up">{fmtInr(stretchPanel.summary?.sum_pnl)}</strong>
                </div>
                <div className="pl-metric">
                  <span className="pl-metric-label">2020</span>
                  <strong className="up">{fmtPct(stretchPanel.summary?.y2020)}</strong>
                </div>
                <div className="pl-metric">
                  <span className="pl-metric-label">2021</span>
                  <strong className="up">{fmtPct(stretchPanel.summary?.y2021)}</strong>
                </div>
                <div className="pl-metric">
                  <span className="pl-metric-label">Locked v2</span>
                  <strong className="up">untouched</strong>
                  <span className="pl-soft">runner +103% 2025</span>
                </div>
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={stretchPanel.chart} margin={{ top: 8, right: 8, left: 0, bottom: 24 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: "#8e8e93", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#8e8e93", fontSize: 11 }} tickFormatter={(v) => `${v}%`} width={44} />
                  <Tooltip
                    contentStyle={tipStyle}
                    formatter={(v: number) => [fmtPct(v), "Year return"]}
                  />
                  <Bar dataKey="ret" radius={[5, 5, 0, 0]}>
                    {(stretchPanel.chart || []).map((entry) => (
                      <Cell key={entry.name} fill={entry.fill || "#30d158"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <p className="pl-soft pl-stretch-claim">{stretchPanel.claim || "Clean PIT standalone panel · research only"}</p>
            </section>
          )}

          <section className="pl-glass pl-panel">
            <div className="pl-panel-head">
              <h2>Ending capital by lane</h2>
              <p className="pl-soft">₹10k start · click a bar for knobs / months</p>
            </div>
            {chartRows.length === 0 ? (
              <p className="muted">No strategy board yet.</p>
            ) : (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart
                  data={chartRows}
                  margin={{ top: 8, right: 8, left: 0, bottom: 40 }}
                  onClick={(state) => {
                    const name = (state as { activeLabel?: string })?.activeLabel;
                    if (!name) return;
                    const hit = strategies.find((s) => s.lane === name);
                    if (hit) setSelectedIter(hit);
                  }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fill: "#8e8e93", fontSize: 10 }} interval={0} angle={-24} textAnchor="end" height={52} />
                  <YAxis tick={{ fill: "#8e8e93", fontSize: 11 }} tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`} width={44} />
                  <Tooltip
                    contentStyle={tipStyle}
                    formatter={(v: number, key: string) =>
                      key === "end" ? [fmtInr(v), "End"] : [fmtInr(v), "PnL"]
                    }
                  />
                  <Bar dataKey="end" radius={[5, 5, 0, 0]} cursor="pointer">
                    {chartRows.map((entry) => (
                      <Cell key={entry.name} fill={entry.fill || ((entry.pnl ?? 0) >= 0 ? "#30d158" : "#ff453a")} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}

            {equityCompare.length > 0 && (
              <div className="pl-equity-block">
                <h3>v2 vs challengers — month path</h3>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={equityCompare} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                    <XAxis dataKey="month" tick={{ fill: "#8e8e93", fontSize: 11 }} />
                    <YAxis tick={{ fill: "#8e8e93", fontSize: 11 }} tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`} width={44} />
                    <Tooltip contentStyle={tipStyle} />
                    <Legend />
                    <Line type="monotone" dataKey="v2" name="v2 locked" stroke="#30d158" strokeWidth={2} dot={false} connectNulls />
                    <Line type="monotone" dataKey="v2_1" name="v2.1" stroke="#64d2ff" strokeWidth={2} dot={false} connectNulls />
                    {"v3" in (equityCompare[0] || {}) && (
                      <Line type="monotone" dataKey="v3" name="v3" stroke="#ffd60a" strokeWidth={2} dot={false} connectNulls />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>

          <div className="pl-grid">
            <section className="pl-glass pl-panel">
              <div className="pl-panel-head">
                <h2>Hero months</h2>
              </div>
              <div className="pl-month-strip">
                {months.length === 0 && <p className="muted">No month path on hero lane.</p>}
                {months.map((m) => (
                  <div key={m.month} className={`pl-month ${(m.month_return_pct ?? m.pnl) >= 0 ? "up" : "down"}`}>
                    <span>{monthLabel(m)}</span>
                    <strong>{m.month_return_pct != null ? fmtPct(m.month_return_pct) : fmtInr(m.pnl)}</strong>
                    <em>
                      {fmtInr(m.pnl)} · {m.n_trades} tx
                    </em>
                  </div>
                ))}
              </div>
            </section>

            <section className="pl-glass pl-panel">
              <div className="pl-panel-head">
                <h2>Mistake briefing</h2>
              </div>
              <p className="pl-soft pl-brief">{briefing?.summary || "Self-learn after each day — bans / size-down / sit-out."}</p>
              {briefing?.exclude_tickers && briefing.exclude_tickers.length > 0 && (
                <p className="pl-soft">
                  Banned: {briefing.exclude_tickers.join(", ")}
                  {briefing.sitout ? " · SIT OUT" : ""}
                  {briefing.size_mult != null && briefing.size_mult < 1 ? ` · size×${briefing.size_mult}` : ""}
                </p>
              )}
              <ul className="pl-list">
                {mistakes.length === 0 && <li className="muted">No mistakes logged yet.</li>}
                {mistakes.slice(0, 12).map((m, i) => (
                  <li key={`${m.ts}-${i}`}>
                    <span className="pl-list-title">
                      {m.asof} · {m.mistake_type}
                      {m.ticker ? ` · ${m.ticker}` : ""}
                    </span>
                    <span className="down">{m.lesson || "—"}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>

          {selectedIter && (
            <section className="pl-glass pl-panel pl-iter-detail">
              <div className="pl-inspector-head pl-row-between">
                <div>
                  <h2>Lane detail</h2>
                  <p>
                    <strong>{"lane" in selectedIter ? selectedIter.lane : selectedIter.label}</strong>
                    {"run_id" in selectedIter && selectedIter.run_id ? ` · ${selectedIter.run_id}` : ""}
                  </p>
                </div>
                <button type="button" className="pl-btn pl-btn-ghost" onClick={() => setSelectedIter(null)}>
                  Close
                </button>
              </div>
              <div className="pl-iter-grid">
                <div>
                  <span className="pl-metric-label">End</span>
                  <strong>{fmtInr("capital_end" in selectedIter ? selectedIter.capital_end : undefined)}</strong>
                </div>
                <div>
                  <span className="pl-metric-label">Return</span>
                  <strong>{fmtPct(selectedIter.total_return_pct)}</strong>
                </div>
                <div>
                  <span className="pl-metric-label">Green</span>
                  <strong>
                    {selectedIter.green_months ?? "—"}/
                    {("months_total" in selectedIter && selectedIter.months_total) || 12}
                  </strong>
                </div>
                <div>
                  <span className="pl-metric-label">Worst</span>
                  <strong>{fmtPct(selectedIter.worst_month_pct)}</strong>
                </div>
                <div>
                  <span className="pl-metric-label">Loss ≤ profits</span>
                  <strong className={"loss_lte_profits" in selectedIter && selectedIter.loss_lte_profits ? "up" : ""}>
                    {"loss_lte_profits" in selectedIter ? (selectedIter.loss_lte_profits ? "Yes" : "No") : "—"}
                  </strong>
                </div>
              </div>
              {"knobs" in selectedIter && selectedIter.knobs && (
                <pre className="pl-payload">{JSON.stringify(selectedIter.knobs, null, 2)}</pre>
              )}
              {"months" in selectedIter && selectedIter.months && selectedIter.months.length > 0 && (
                <div className="pl-month-strip" style={{ marginTop: "0.75rem" }}>
                  {selectedIter.months.map((m) => (
                    <div key={m.month} className={`pl-month ${(m.month_return_pct ?? m.pnl) >= 0 ? "up" : "down"}`}>
                      <span>{monthLabel(m)}</span>
                      <strong>{fmtPct(m.month_return_pct)}</strong>
                      <em>{fmtInr(m.pnl)}</em>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}

      {tab === "swarm" && (
        <>
          {matrix.days.length > 0 && (
            <section className="pl-glass pl-panel">
              <div className="pl-panel-head">
                <h2>Agent × decision</h2>
                <p className="pl-soft">Click a cell to inspect that day</p>
              </div>
              <div className="pl-matrix-wrap">
                <div className="pl-matrix" style={{ gridTemplateColumns: `8.5rem repeat(${matrix.days.length}, 2rem)` }}>
                  <div className="pl-matrix-corner" />
                  {matrix.days.map((d, i) => (
                    <button
                      key={`h-${d.asof}-${i}`}
                      type="button"
                      className={`pl-matrix-day ${selected?.asof === d.asof && selected?.ticker === d.ticker ? "active" : ""}`}
                      title={`${d.asof} ${d.ticker}`}
                      onClick={() => setSelected(d)}
                    >
                      {(d.asof || "").slice(5)}
                    </button>
                  ))}
                  {matrix.rows.map((row) => (
                    <div key={row.agent} style={{ display: "contents" }}>
                      <div className={`pl-matrix-agent ${STUB_AGENTS.has(row.agent) ? "stub" : ""}`}>{row.agent}</div>
                      {row.cells.map((c, j) => (
                        <button
                          key={`${row.agent}-${j}`}
                          type="button"
                          className={`pl-matrix-cell ${c.vote}${c.stub ? " stub" : ""}${
                            selected?.asof === matrix.days[j]?.asof && selected?.ticker === matrix.days[j]?.ticker
                              ? " active"
                              : ""
                          }`}
                          title={`${row.agent}: ${c.vote} — ${c.reason}`}
                          onClick={() => setSelected(matrix.days[j])}
                        >
                          {voteGlyph(c.vote)}
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            </section>
          )}

          <div className="pl-grid pl-grid-wide">
            <section className="pl-glass pl-panel">
              <div className="pl-panel-head">
                <h2>Decision tape</h2>
              </div>
              <ul className="pl-tape">
                {decisions.length === 0 && <li className="muted">No decisions yet.</li>}
                {decisions.map((d, i) => (
                  <li key={`${d.ts}-${i}`}>
                    <button
                      type="button"
                      className={`pl-tape-row ${
                        selected?.ts === d.ts && selected?.asof === d.asof && selected?.ticker === d.ticker ? "active" : ""
                      }`}
                      onClick={() => setSelected(d)}
                    >
                      <span className={`pl-choice ${d.choice}`}>{d.choice}</span>
                      <span className="pl-tape-main">
                        <strong>{d.ticker}</strong>
                        <em>{d.asof}</em>
                      </span>
                      <span className="pl-tape-meta">
                        {(d.swarm_messages || []).length} agents · {d.skip_reason || d.primary?.reason || "—"}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>

            <section className="pl-glass pl-panel pl-inspector">
              <div className="pl-panel-head">
                <h2>Inspector</h2>
              </div>
              {!selected && <p className="muted">Select a decision.</p>}
              {selected && (
                <div className="pl-detail">
                  <div className="pl-inspector-head">
                    <p>
                      <strong>{selected.ticker}</strong> · {selected.asof} · {selected.choice}
                    </p>
                    <p className="muted">
                      {selected.primary?.side || "—"} · {selected.primary?.reason || "—"} · conf{" "}
                      {selected.primary?.confidence?.toFixed?.(2) ?? "—"}
                    </p>
                    <p className="muted">
                      Agreement:{" "}
                      <strong className={selected.swarm_agreement?.tradeable ? "up" : "down"}>
                        {selected.swarm_agreement?.tradeable ? "tradeable" : "blocked"}
                      </strong>
                      {" · "}
                      {selected.swarm_agreement?.reason}
                    </p>
                    <div className="pl-scoreboard">
                      <span className="pl-score take">take {voteCounts.take}</span>
                      <span className="pl-score skip">skip {voteCounts.skip}</span>
                      <span className="pl-score annotate">annotate {voteCounts.annotate}</span>
                    </div>
                    <div className="pl-filter-row">
                      {(["all", "take", "skip", "annotate"] as const).map((f) => (
                        <button
                          key={f}
                          type="button"
                          className={`pl-filter ${agentFilter === f ? "active" : ""}`}
                          onClick={() => setAgentFilter(f)}
                        >
                          {f}
                        </button>
                      ))}
                    </div>
                  </div>

                  {(chartBusy || priceChart) && (
                    <div className="pl-price-chart">
                      <h3>Price · markers</h3>
                      {chartBusy && <p className="muted">Loading…</p>}
                      {!chartBusy && priceChart && (
                        <DetailPriceChart
                          prices={priceChart.prices || []}
                          height={240}
                          markers={priceChart.markers || []}
                          entryPrice={priceChart.entry_price}
                        />
                      )}
                    </div>
                  )}

                  <div className="pl-agent-cards">
                    {dayAgents.map((m, i) => {
                      const stub = isStub(m);
                      return (
                        <article key={`${m.agent}-${i}`} className={`pl-agent-card${stub ? " stub" : ""}`}>
                          <header>
                            <h3>{m.agent}</h3>
                            <span className={voteClass(m.vote)}>{m.vote || "—"}</span>
                            {stub ? <span className="pl-stub-tag">stub</span> : null}
                          </header>
                          <p className="pl-reason">{m.reason || "—"}</p>
                          {m.payload && Object.keys(m.payload).length > 0 && (
                            <details className="pl-payload-details">
                              <summary>payload</summary>
                              <pre className="pl-payload">{JSON.stringify(m.payload, null, 2)}</pre>
                            </details>
                          )}
                        </article>
                      );
                    })}
                  </div>
                </div>
              )}
            </section>
          </div>
        </>
      )}

      {tab === "ledger" && (
        <>
          <section className="pl-glass pl-panel">
            <div className="pl-panel-head">
              <h2>Trades</h2>
              <p className="pl-soft">Click a row → swarm inspector + price markers</p>
            </div>
            <div className="pl-table-wrap">
              <table className="pl-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Ticker</th>
                    <th>Side</th>
                    <th>PnL</th>
                    <th>Lev</th>
                    <th>Why</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.length === 0 && (
                    <tr>
                      <td colSpan={6} className="muted">
                        No trades yet.
                      </td>
                    </tr>
                  )}
                  {trades.map((t, i) => (
                    <tr
                      key={`${t.ts}-${i}`}
                      className="pl-row-click"
                      onClick={() => {
                        void loadChart(t.ticker, t.asof);
                        const hit = decisions.find(
                          (d) =>
                            d.asof === t.asof &&
                            String(d.ticker || "").toUpperCase() === String(t.ticker || "").toUpperCase()
                        );
                        if (hit) selectDecision(hit);
                        else setTab("swarm");
                      }}
                    >
                      <td>{t.asof}</td>
                      <td>{t.ticker}</td>
                      <td>{t.side}</td>
                      <td className={(t.pnl || 0) >= 0 ? "up" : "down"}>
                        {fmtInr(t.pnl)} ({fmtPct(t.pnl_pct)})
                      </td>
                      <td>{t.leverage != null ? `${t.leverage}×` : "—"}</td>
                      <td>{t.signal_reason || t.family}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <div className="pl-grid">
            <section className="pl-glass pl-panel">
              <div className="pl-panel-head">
                <h2>Iterations / runs</h2>
              </div>
              <ul className="pl-list">
                {iterList.length === 0 && <li className="muted">No iterations yet</li>}
                {iterList.map((it, i) => (
                  <li key={`${it.ts}-${it.label}-${i}`} className={it.keep || it.goal_met ? "keep" : ""}>
                    <button type="button" className="pl-iter-btn" onClick={() => setSelectedIter(it)}>
                      <span className="pl-list-title">{it.label || it.lane || "run"}</span>
                      <span>
                        {it.green_months ?? "—"}/12 · {fmtPct(it.total_return_pct)}
                        {it.capital_end != null ? ` · ${fmtInr(it.capital_end)}` : ""}
                      </span>
                      <span className="pl-chip">{it.keep || it.goal_met ? "KEEP" : "open"}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>

            <section className="pl-glass pl-panel">
              <div className="pl-panel-head">
                <h2>Recent mistakes</h2>
              </div>
              <ul className="pl-list">
                {mistakes.length === 0 && <li className="muted">Empty</li>}
                {mistakes.slice(0, 20).map((m, i) => (
                  <li key={`${m.ts}-L-${i}`}>
                    <span className="pl-list-title">
                      {m.asof} · {m.mistake_type} {m.ticker || ""}
                    </span>
                    <span className="down">{m.lesson || "—"}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}

      <p className="pl-foot">{disclaimer || "Paper/sim Pattern Forge — not investment advice."}</p>
    </div>
  );
}
