import { useEffect, useState } from "react";
import { apiFetch } from "../api";

export default function CalibrationPage() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    apiFetch("/stats/calibration").then(setData);
  }, []);

  if (!data) return <p>Loading…</p>;

  return (
    <div className="card">
      <h2>Calibration</h2>
      <p className="warn">{data.disclaimer}</p>
      <p>Scorer: {data.scorer_version}</p>
      <table className="table">
        <thead><tr><th>Tier</th><th>Count</th><th>Realized WR</th><th>Median Return</th></tr></thead>
        <tbody>
          {Object.entries(data.buckets).map(([tier, bucket]: [string, any]) => (
            <tr key={tier}>
              <td>{tier}</td>
              <td>{bucket.count}</td>
              <td>{bucket.realized_win_rate != null ? `${(bucket.realized_win_rate * 100).toFixed(1)}%` : "—"}</td>
              <td>{bucket.median_return != null ? `${(bucket.median_return * 100).toFixed(2)}%` : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
