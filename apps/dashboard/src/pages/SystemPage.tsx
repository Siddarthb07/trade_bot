import { useEffect, useState } from "react";
import { apiFetch } from "../api";

export default function SystemPage() {
  const [system, setSystem] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);

  useEffect(() => {
    apiFetch("/system").then(setSystem);
    apiFetch<{ items: any[] }>("/ingestion/runs").then((d) => setRuns(d.items));
  }, []);

  if (!system) return <p>Loading…</p>;

  return (
    <div className="grid">
      <section className="card">
        <h2>System Health</h2>
        <pre>{JSON.stringify(system.health, null, 2)}</pre>
        <p>Signals total: {system.signals_total}</p>
        <p>Queue depth: {system.queue_depth}</p>
        <p>Last alert: {system.last_alert ? `${system.last_alert.channel} · ${system.last_alert.status}` : "—"}</p>
      </section>
      <section className="card">
        <h3>Ingestion Runs</h3>
        <table className="table">
          <thead><tr><th>Job</th><th>Status</th><th>New</th><th>Started</th><th>Error</th></tr></thead>
          <tbody>
            {runs.map((r, i) => (
              <tr key={i}>
                <td>{r.job_name}</td>
                <td>{r.status}</td>
                <td>{r.rows_new}</td>
                <td>{r.started_at}</td>
                <td>{r.error || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
