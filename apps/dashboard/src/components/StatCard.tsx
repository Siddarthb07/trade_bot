import { fmtPct } from "../utils/format";

export default function StatCard({
  label,
  value,
  sub,
  accent = "blue",
  trend,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: "blue" | "green" | "purple" | "amber";
  trend?: string;
}) {
  return (
    <div className={`stat-card accent-${accent}`}>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      {sub && <span className="stat-sub">{sub}</span>}
      {trend && <span className="stat-trend">{trend}</span>}
    </div>
  );
}

export function ScorePill({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="score-pill">
      <span>{label}</span>
      <strong>{fmtPct(value)}</strong>
    </div>
  );
}
