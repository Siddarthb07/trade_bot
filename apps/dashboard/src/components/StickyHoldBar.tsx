import { HoldBanner } from "./HoldTimeline";
import { TimeframeInfo } from "../utils/timeframe";

export default function StickyHoldBar({ tf, label }: { tf: TimeframeInfo; label?: string }) {
  if (!tf.hold_days) return null;
  return (
    <div className="sticky-hold-bar">
      {label && <span className="sticky-label">{label}</span>}
      <HoldBanner tf={tf} compact />
    </div>
  );
}
