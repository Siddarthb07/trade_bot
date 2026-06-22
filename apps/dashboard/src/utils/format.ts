/** Format helpers for dashboard. */

export function fmtPct(v: number | null | undefined, digits = 0) {
  if (v == null) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function fmtExp(v: number | null | undefined) {
  if (v == null) return "—";
  return `+${(v * 100).toFixed(0)}%`;
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
