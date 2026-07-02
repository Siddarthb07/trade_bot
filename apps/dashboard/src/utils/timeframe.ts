/** Timeframe helpers for dashboard (mirrors API return_distribution). */

import type { HoldDisplayMode } from "../hooks/useHoldPrefs";

export interface TimeframeInfo {
  hold_days?: number;
  hold_label_short?: string;
  hold_label_long?: string;
  entry_date?: string;
  review_date?: string;
  review_date_label?: string;
  entry_date_label?: string;
  entry_date_full?: string;
  exit_date?: string;
  exit_date_label?: string;
  exit_date_full?: string;
  exit_window_label?: string;
  timeframe_tier?: string;
  days_elapsed?: number;
  days_remaining?: number;
  countdown_label?: string;
  hold_status?: string;
  sell_horizon_label?: string;
  expected_return_pct?: number;
}

export function tfFromDist(dist?: Record<string, unknown> | null): TimeframeInfo {
  if (!dist) return {};
  return dist as TimeframeInfo;
}

export function formatHoldLabel(tf: TimeframeInfo, mode: HoldDisplayMode = "both"): string {
  const days = tf.hold_days;
  if (!days) return tf.hold_label_long || tf.sell_horizon_label || "—";
  const short = tf.hold_label_short || `~${Math.max(1, Math.round(days / 7))} weeks`;
  if (mode === "days") return `Hold ${days} days`;
  if (mode === "weeks") return short.startsWith("Hold") ? short : `Hold ${short}`;
  return tf.hold_label_long || `Hold ${days} days · ${short}`;
}

export function holdSummary(tf: TimeframeInfo, mode: HoldDisplayMode = "both"): string {
  return formatHoldLabel(tf, mode);
}

export function exitSummary(tf: TimeframeInfo): string {
  if (tf.exit_date_full) return `Sell by ${tf.exit_date_full}`;
  if (tf.exit_date_label) return `Sell by ${tf.exit_date_label}`;
  return "—";
}

export function reviewSummary(tf: TimeframeInfo): string {
  if (tf.review_date_label) return `Review ${tf.review_date_label}`;
  return "—";
}

export function timelineProgress(tf: TimeframeInfo): number {
  const hold = tf.hold_days || 0;
  const elapsed = tf.days_elapsed ?? 0;
  if (hold <= 0) return 0;
  return Math.min(100, Math.max(0, (elapsed / hold) * 100));
}
