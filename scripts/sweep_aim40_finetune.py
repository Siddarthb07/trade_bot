"""Fine-tune sleeve for aim40 band."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "scripts"))

from run_pattern_forge_daily_swing_2025 import run_daily_benchmark

cands = []
for lev, sleeve in ((8, 0.27), (8, 0.28), (9, 0.22), (9, 0.25)):
  print(f"\n=== lev {lev} sleeve {sleeve} ===", flush=True)
  r = run_daily_benchmark(
    knobs={
      "leverage": float(lev),
      "sleeve_frac": float(sleeve),
      "long_only": True,
      "min_score": 0.005,
      "r1_lo": 0.005,
      "r1_hi": 0.06,
      "top_k": 1,
      "learn_mistakes": True,
      "breadth_scale": False,
      "use_breadth_veto": False,
      "reset_mistakes": True,
      "promote_summary": False,
      "lane": f"aim40_l{lev}_s{sleeve}",
      "max_daily_loss_pct": 8.0,
    }
  )
  row = {
    "lev": lev,
    "sleeve": sleeve,
    "ret": r["total_return_pct"],
    "green": r["green_months"],
    "worst": r["worst_month_pct"],
    "run_id": r["run_id"],
    "in_band": 40.0 <= float(r["total_return_pct"]) <= 50.0,
  }
  cands.append(row)
  print(
    f"RESULT lev={lev} sleeve={sleeve} ret={r['total_return_pct']:+.2f}% "
    f"green={r['green_months']} worst={r['worst_month_pct']:+.2f}% in_band={row['in_band']}",
    flush=True,
  )

# Prefer in-band with best (least bad) worst-month
in_band = [c for c in cands if c["in_band"]]
pick = min(in_band, key=lambda c: abs(c["worst"])) if in_band else max(cands, key=lambda c: c["ret"])
print("PICK", pick, flush=True)
Path(ROOT / "models" / "pattern_forge" / "aim40_finetune.json").write_text(
  json.dumps({"cands": cands, "pick": pick}, indent=2), encoding="utf-8"
)
