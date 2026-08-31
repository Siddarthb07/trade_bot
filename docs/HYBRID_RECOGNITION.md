# Hybrid Recognition (Godfather)

NSE-only recognition stack as a **deterministic specialist swarm**. No LLMs on the fire path.

## KPI

Compound keepable equity / skip unstructured days. 8–10%/day on session-close remains oracle-unreachable (see `DAY_SIM_METHODS_LOG.md` in this clone).

## Paper map (live vs stub)

| Layer | Module | Paper / method | Status |
|---|---|---|---|
| L0 | `geometry.py` | GHLZ 2018 r1; HAR-RV; OR width as state | Live (features) |
| L1 | `detectors/hmm.py` | Hamilton 1989 filtered P | Live (lightweight filter) |
| L1 | `detectors/hurst.py` | Peters FMH R/S | Live |
| L1 | `detectors/changepoint.py` | CUSUM / BOCPD-lite | Live |
| L1 | `detectors/jumps.py` | BN-S bipower | Live (coarse) |
| L2 | `models/triple_barrier.py` | AFML Ch. 3 | Live |
| L2 | `models/meta_label.py` | AFML meta-labeling | Heuristic P(take); veto only |
| L2 | `swarm/similarity.py` | Ye & Keogh DTW/shapelets | Live |
| L2 | `swarm/line_geometry.py` | OR/VWAP/pivot geometry | Live |
| L3 | `swarm/supervisor.py` | MoE + correlated-vote collapse | Live |
| L4 | `allocator.py` | Moreira–Muir vol-target; fractional Kelly | Live (reduce-only vs guards) |
| Stub | `stubs/vpin.py` | Easley et al. | `insufficient_data` |
| Stub | `stubs/hawkes.py` | Hawkes | `insufficient_data` on NSE |
| Stub | `stubs/kyle.py` | Kyle λ | `insufficient_data` |

## Ecology split

- `nse` — product path
- `crypto` / `meme` — research only; see plan nested loops (Liu–Tsyvinski; Cong wash trading)

## Lookahead

HMM uses **filtered** posteriors only. `filtered_at_t(closes, t)` ignores bars after `t`.

## Agent roster (10 roles)

TickerWorker×N, Geometry, Similarity, LineGeometry, Regime, MetaLabel, Cost, Decay, Supervisor, Risk (`session_guard`).
