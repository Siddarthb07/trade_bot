"""Append-only decision receipts (signal → gate → size → fill) + model pin helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RECEIPT_PATH = ROOT / "models" / "decision_receipts.jsonl"
PIN_PATH = ROOT / "models" / "model_pin.json"


def current_model_pin() -> dict[str, Any]:
  """Pin adaptive profiles + optional LightGBM meta for order audit."""
  pin: dict[str, Any] = {
    "pinned_at": datetime.now(timezone.utc).isoformat(),
    "adaptive_profiles": None,
    "adaptive_eligible": [],
    "lgbm_meta": None,
  }
  profiles = ROOT / "models" / "ticker_adaptive_profiles.json"
  if profiles.exists():
    try:
      data = json.loads(profiles.read_text(encoding="utf-8"))
      pin["adaptive_profiles"] = data.get("generated_at")
      pin["adaptive_eligible"] = list(data.get("eligible_tickers") or [])
      pin["adaptive_target_hit_pct"] = data.get("target_hit_pct")
    except Exception:
      pass
  meta = ROOT / "models" / "lgbm_meta.json"
  if meta.exists():
    try:
      pin["lgbm_meta"] = json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
      pass
  if PIN_PATH.exists():
    try:
      frozen = json.loads(PIN_PATH.read_text(encoding="utf-8"))
      pin["frozen_pin"] = frozen
    except Exception:
      pass
  return pin


def freeze_model_pin() -> dict[str, Any]:
  """Write models/model_pin.json so live can rollback to this snapshot ref."""
  pin = current_model_pin()
  PIN_PATH.parent.mkdir(parents=True, exist_ok=True)
  PIN_PATH.write_text(json.dumps(pin, indent=2), encoding="utf-8")
  return pin


def append_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
  row = {
    **receipt,
    "ts": receipt.get("ts") or datetime.now(timezone.utc).isoformat(),
    "model_pin": receipt.get("model_pin") or current_model_pin(),
    "disclaimer": "Not investment advice. Personal research audit log only.",
  }
  RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
  with RECEIPT_PATH.open("a", encoding="utf-8") as f:
    f.write(json.dumps(row, default=str) + "\n")
  return row


def recent_receipts(limit: int = 50) -> list[dict[str, Any]]:
  if not RECEIPT_PATH.exists():
    return []
  lines = RECEIPT_PATH.read_text(encoding="utf-8").strip().splitlines()
  out: list[dict[str, Any]] = []
  for line in lines[-limit:]:
    try:
      out.append(json.loads(line))
    except Exception:
      continue
  out.reverse()
  return out
