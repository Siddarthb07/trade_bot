import { DataMaturityInfo } from "../api";

const STATUS_CLASS: Record<string, string> = {
  too_new: "maturity-new",
  maturing: "maturity-wait",
  labeled: "maturity-ready",
  partial: "maturity-partial",
};

export default function DataMaturityBadge({ maturity }: { maturity?: DataMaturityInfo | null }) {
  if (!maturity) return null;
  const cls = STATUS_CLASS[maturity.status] || "maturity-partial";
  return (
    <div className={`data-maturity ${cls}`} title={maturity.detail}>
      <span className="maturity-label">{maturity.label}</span>
      {maturity.readiness_pct < 100 && maturity.status !== "labeled" && (
        <span className="maturity-bar">
          <span style={{ width: `${maturity.readiness_pct}%` }} />
        </span>
      )}
    </div>
  );
}
