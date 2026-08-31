import type { BarInterval, Lane } from "./format";

export type BenchWindow = { id: string; label?: string };

type Props = {
  mode: "day" | "window";
  lane: Lane;
  asof: string;
  windowId: string;
  benchmarks: BenchWindow[];
  capital: number;
  maxPositions: number;
  barInterval: BarInterval;
  busy: boolean;
  tableView: boolean;
  hideLane?: boolean;
  runLabel?: string;
  onMode: (m: "day" | "window") => void;
  onLane: (l: Lane) => void;
  onAsof: (v: string) => void;
  onWindowId: (v: string) => void;
  onCapital: (v: number) => void;
  onMaxPositions: (v: number) => void;
  onBarInterval: (v: BarInterval) => void;
  onTableView: (v: boolean) => void;
  onRun: () => void;
};

export default function HybridRunnerBar({
  mode,
  lane,
  asof,
  windowId,
  benchmarks,
  capital,
  maxPositions,
  barInterval,
  busy,
  tableView,
  hideLane = false,
  runLabel = "Run hybrid sim",
  onMode,
  onLane,
  onAsof,
  onWindowId,
  onCapital,
  onMaxPositions,
  onBarInterval,
  onTableView,
  onRun,
}: Props) {
  return (
    <section className="hybrid-runner-bar">
      <div className="tabs">
        <button type="button" className={mode === "day" ? "active" : ""} onClick={() => onMode("day")}>
          Day
        </button>
        <button type="button" className={mode === "window" ? "active" : ""} onClick={() => onMode("window")}>
          Window
        </button>
        {!hideLane &&
          (["product", "stretch", "research"] as Lane[]).map((l) => (
            <button key={l} type="button" className={lane === l ? "active" : ""} onClick={() => onLane(l)}>
              {l}
            </button>
          ))}
        {hideLane && (
          <button type="button" className="active" disabled>
            copy_bulk_pro
          </button>
        )}
      </div>
      <div className="runner-row dense">
        {mode === "day" ? (
          <label>
            Asof
            <input value={asof} onChange={(e) => onAsof(e.target.value)} />
          </label>
        ) : (
          <label>
            Window
            <select value={windowId} onChange={(e) => onWindowId(e.target.value)}>
              {benchmarks.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.id}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          Capital ₹
          <input
            type="number"
            value={capital}
            min={1000}
            step={1000}
            onChange={(e) => onCapital(Number(e.target.value) || 10000)}
          />
        </label>
        <label>
          Positions
          <select value={maxPositions} onChange={(e) => onMaxPositions(Number(e.target.value))}>
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <label>
          Bar freq
          <select value={barInterval} onChange={(e) => onBarInterval(e.target.value as BarInterval)}>
            <option value="5m">5m</option>
            <option value="1m">1m</option>
            <option value="15m">15m</option>
          </select>
        </label>
        <label className="toggle-table">
          <input type="checkbox" checked={tableView} onChange={(e) => onTableView(e.target.checked)} />
          Table view
        </label>
        <button type="button" className="primary pressable" disabled={busy} onClick={onRun}>
          {busy ? "Simulating…" : runLabel}
        </button>
      </div>
    </section>
  );
}
