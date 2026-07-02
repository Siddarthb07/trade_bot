/** Metric builders — separate hold vs profit views. */

import { LiveThemePick, SignalItem } from "../api";
import { fmtDateLabel, fmtExp, fmtPct, fmtRatio, fmtTrackRecord, fmtValue } from "./format";
import { TimeframeInfo, tfFromDist } from "./timeframe";
import { Metric } from "../components/StockPanel";

export type PickView = "hold" | "profit";

function tradeDateMetrics(tf: TimeframeInfo, entryFallback?: string): Metric[] {
  const buy =
    tf.entry_date_full ||
    tf.entry_date_label ||
    fmtDateLabel(entryFallback) ||
    fmtDateLabel(tf.entry_date);
  return [
    { label: "Buy / entry", value: buy },
    { label: "Sell by", value: tf.exit_date_full || tf.exit_date_label || "—" },
    { label: "Review", value: tf.review_date_label || "—" },
    { label: "Exit window", value: tf.exit_window_label || "—" },
    { label: "Days left", value: tf.countdown_label || (tf.days_remaining != null ? `${tf.days_remaining} days` : "—") },
  ];
}

export function demandHoldMetrics(p: LiveThemePick, tf: TimeframeInfo): Metric[] {
  return [
    ...tradeDateMetrics(tf, p.signal_date),
    { label: "Hold", value: tf.hold_label_short || `${tf.hold_days ?? "—"} days` },
    { label: "Tier", value: p.tier || "—" },
    { label: "Theme heat", value: fmtPct(p.theme_heat) },
  ];
}

export function demandProfitMetrics(p: LiveThemePick, tf: TimeframeInfo): Metric[] {
  const f = p.fundamentals || {};
  return [
    ...tradeDateMetrics(tf, p.signal_date),
    { label: "Est. return", value: fmtExp(p.expected_return_pct), accent: true },
    { label: "Confidence", value: fmtPct(p.calibrated_probability, 1) },
    { label: "P/E (TTM)", value: fmtRatio(f.trailing_pe) },
    { label: "Fwd P/E", value: fmtRatio(f.forward_pe) },
    { label: "EBITDA mgn", value: fmtPct(f.ebitda_margin, 1) },
    { label: "Net margin", value: fmtPct(f.profit_margin, 1) },
    { label: "Rev growth", value: fmtPct(f.revenue_growth, 1) },
    { label: "ROE", value: fmtPct(f.return_on_equity, 1) },
  ];
}

export function bulkHoldMetrics(s: SignalItem, tf: TimeframeInfo): Metric[] {
  const backing = s.investor_backing;
  return [
    ...tradeDateMetrics(tf, s.disclosed_at),
    ...(backing ? [
      { label: "Total backed", value: fmtValue(backing.total_value, s.market), accent: true },
      { label: "Investors", value: String(backing.investor_count) },
      { label: "Deals", value: String(backing.deal_count) },
    ] : [
      { label: "Investor", value: s.entity?.slice(0, 28) || "—" },
      { label: "Deal size", value: fmtValue(s.value, s.market) },
    ]),
    { label: "Hold", value: String(tf.hold_label_short || tf.hold_days || "—") },
    { label: "Investor trades", value: s.n_trades != null ? String(s.n_trades) : "—" },
  ];
}

export function bulkProfitMetrics(s: SignalItem, tf: TimeframeInfo): Metric[] {
  const dist = s.return_distribution || {};
  const f = (dist.fundamentals as Record<string, number | null>) || {};
  const backing = s.investor_backing;
  return [
    ...tradeDateMetrics(tf, s.disclosed_at),
    ...(backing ? [
      { label: "Total backed", value: fmtValue(backing.total_value, s.market), accent: true },
      { label: "Investors", value: String(backing.investor_count) },
    ] : []),
    { label: "Est. return", value: fmtExp(dist.expected_return_pct as number), accent: !backing },
    { label: "Confidence", value: fmtPct(s.calibrated_probability, 1) },
    { label: "Lead investor WR", value: fmtTrackRecord(s.historical_win_rate, s.n_trades) },
    { label: "Lead median ret.", value: fmtExp(dist.median as number) },
    ...(backing?.aggregate_win_rate != null ? [
      { label: "Buyers avg WR", value: fmtTrackRecord(backing.aggregate_win_rate, backing.tracked_past_trades) },
    ] : []),
    { label: "P/E (TTM)", value: fmtRatio(f.trailing_pe) },
    { label: "Net margin", value: fmtPct(f.profit_margin, 1) },
    { label: "EBITDA mgn", value: fmtPct(f.ebitda_margin, 1) },
    { label: "Rev growth", value: fmtPct(f.revenue_growth, 1) },
  ];
}

export function pickRationale(p: LiveThemePick): string | undefined {
  return p.return_rationale;
}

export function signalRationale(s: SignalItem): string | undefined {
  return s.return_distribution?.return_rationale as string | undefined;
}

export function signalTf(s: SignalItem): TimeframeInfo {
  return tfFromDist(s.return_distribution);
}
