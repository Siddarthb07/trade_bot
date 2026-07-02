/** Timeframe helpers for dashboard (mirrors API return_distribution). */

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

export function holdSummary(tf: TimeframeInfo): string {
  if (tf.hold_label_long) return tf.hold_label_long;
  if (tf.hold_days) return `Hold ${tf.hold_days} days`;
  return tf.sell_horizon_label || "—";
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
