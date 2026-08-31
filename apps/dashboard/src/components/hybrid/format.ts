/** Shared formatters for Hybrid Lab cards. */

export type Lane = "product" | "stretch" | "research";
export type LabMode = "session" | "book" | "strategies" | "forward";
export type BarInterval = "1m" | "5m" | "15m";

export function fmtInr(n: number | null | undefined, digits = 2) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: digits })}`;
}

export function fmtPct(n: number | null | undefined, digits = 2) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

export function fmtNum(n: number | null | undefined, digits = 4) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toFixed(digits);
}

export function clsPnL(n: number | null | undefined) {
  if (n == null) return "";
  return Number(n) >= 0 ? "pos" : "neg";
}

export function barsToPrices(bars: any[] | undefined) {
  if (!bars?.length) return [];
  return bars.map((b) => ({
    date: String(b.ts || b.date || "").slice(0, 19),
    close: Number(b.close),
    high: b.high != null ? Number(b.high) : undefined,
    low: b.low != null ? Number(b.low) : undefined,
    open: b.open != null ? Number(b.open) : undefined,
    volume: b.volume != null ? Number(b.volume) : undefined,
  }));
}
