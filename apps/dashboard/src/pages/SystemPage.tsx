import { useEffect, useState } from "react";
import { apiFetch } from "../api";

export default function SystemPage() {
  const [system, setSystem] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const [sys, ing] = await Promise.all([
          apiFetch("/system"),
          apiFetch<{ items: any[] }>("/ingestion/runs"),
        ]);
        setSystem(sys);
        setRuns(ing.items);
      } catch (e) {
        console.error(e);
        setError("Could not load system status — API may be busy. Try refreshing in a minute.");
      }
    }
    load();
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!system) return <p>Loading…</p>;

  const ml = system.ml_model;

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
        <h3>ML Model (Phase 2/5)</h3>
        {!ml ? (
          <p className="muted">No model trained yet. Run <code>POST /internal/train</code> or wait for Sunday 5:30 AM IST job.</p>
        ) : (
          <>
            <p>Status: <strong>{ml.status}</strong></p>
            {ml.n_samples != null && <p>Samples: {ml.n_samples}</p>}
            {ml.test_accuracy != null && <p>Test accuracy: {(ml.test_accuracy * 100).toFixed(1)}%</p>}
            {ml.trained_at && <p className="muted">Trained: {ml.trained_at}</p>}
            {ml.hold_priors && (
              <pre className="code-block">{JSON.stringify(ml.hold_priors, null, 2)}</pre>
            )}
          </>
        )}
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
