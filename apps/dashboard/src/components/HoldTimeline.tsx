import { TimeframeInfo, formatHoldLabel, timelineProgress } from "../utils/timeframe";
import { useHoldPrefs } from "../hooks/useHoldPrefs";

export default function HoldTimeline({ tf, compact }: { tf: TimeframeInfo; compact?: boolean }) {
  if (!tf.hold_days) return null;
  const pct = timelineProgress(tf);
  const status = tf.hold_status || "active";
  const statusClass = `hold-status hold-${status}`;

  return (
    <div className={`hold-timeline${compact ? " compact" : ""}`}>
      <div className="hold-timeline-labels">
        <span>Entry {tf.entry_date_label || tf.entry_date_full || "—"}</span>
        <span>Review {tf.review_date_label || "—"}</span>
        <span>Exit {tf.exit_date_label || "—"}</span>
      </div>
      <div className="hold-track">
        <div className="hold-fill" style={{ width: `${pct}%` }} />
        <span className="hold-marker review" style={{ left: "50%" }} title="Review" />
        <span className="hold-marker exit" style={{ left: "100%" }} title="Exit" />
      </div>
      <div className="hold-foot">
        <span className={statusClass}>{tf.countdown_label || `${tf.days_remaining ?? "—"} days left`}</span>
        {tf.exit_window_label && <span className="muted">Window {tf.exit_window_label}</span>}
        {tf.timeframe_tier && <span className="tag">{tf.timeframe_tier} hold</span>}
      </div>
    </div>
  );
}

export function HoldBanner({ tf, compact }: { tf: TimeframeInfo; compact?: boolean }) {
  const mode = useHoldPrefs();
  if (!tf.hold_days) return null;
  const entry = tf.entry_date_full || tf.entry_date_label;
  return (
    <div className={`hold-banner${compact ? " compact" : ""}`}>
      <strong>{formatHoldLabel(tf, mode)}</strong>
      {entry && <span>Buy {entry}</span>}
      <span>Sell by {tf.exit_date_full || tf.exit_date_label}</span>
      <span>Review {tf.review_date_label}</span>
      <span className={`hold-badge hold-${tf.hold_status || "active"}`}>{tf.countdown_label}</span>
    </div>
  );
}
