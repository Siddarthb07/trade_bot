/** Format helpers for dashboard. */

export function fmtPct(v: number | null | undefined, digits = 0) {
  if (v == null) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function fmtExp(v: number | null | undefined, digits = 1) {
  if (v == null) return "—";
  const pct = v * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(digits)}%`;
}

export function fmtRatio(v: number | null | undefined, digits = 1) {
  if (v == null) return "—";
  return v.toFixed(digits);
}

export function fmtDateLabel(iso?: string | null, short = false) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, short
    ? { day: "numeric", month: "short" }
    : { day: "numeric", month: "short", year: "numeric" });
}

export function fmtValue(v: number | null | undefined, market = "IN") {
  if (v == null) return "—";
  if (market === "IN") {
    if (v >= 1e7) return `₹${(v / 1e7).toFixed(1)}Cr`;
    if (v >= 1e5) return `₹${(v / 1e5).toFixed(1)}L`;
    return `₹${v.toLocaleString()}`;
  }
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

export function tierClass(tier?: string) {
  return `tier ${(tier || "").toLowerCase()}`;
}

export const TIER_COLORS: Record<string, string> = {
  HIGH: "#ff6b6b",
  MEDIUM: "#ffd166",
  LOW: "#8de969",
};

export const CHART_COLORS = ["#6366f1", "#22d3ee", "#a78bfa", "#34d399", "#fbbf24", "#f472b6", "#60a5fa"];

/** Past investor track record — distinguish no data vs 0% on small samples. */
export function fmtTrackRecord(
  winRate: number | null | undefined,
  nTrades: number | null | undefined,
) {
  if (nTrades == null || nTrades === 0) return "No history yet";
  if (winRate == null) return `${nTrades} past trades`;
  return `${(winRate * 100).toFixed(0)}% win (${nTrades} trades)`;
}
