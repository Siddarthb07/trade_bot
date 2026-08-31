"""Ledger smoke tests — no network."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.pattern_forge.ledger import log_decision, log_trade, recent_decisions, write_summary, load_summary


def test_ledger_append_and_summary(tmp_path, monkeypatch):
  import processor.pattern_forge.ledger as led

  monkeypatch.setattr(led, "LEDGER_DIR", tmp_path)
  monkeypatch.setattr(led, "DECISIONS_PATH", tmp_path / "decisions.jsonl")
  monkeypatch.setattr(led, "TRADES_PATH", tmp_path / "trades.jsonl")
  monkeypatch.setattr(led, "LATEST_SUMMARY", tmp_path / "latest_summary.json")

  log_decision(
    {
      "asof": "2025-10-01",
      "ticker": "RELIANCE.NS",
      "family": "pattern_candle",
      "choice": "skip",
      "skip_reason": "flat_primary",
    }
  )
  log_trade({"asof": "2025-10-01", "ticker": "RELIANCE.NS", "pnl": 12.5, "side": "long"})
  write_summary({"status": "ok", "green_months": 1})
  assert recent_decisions(5)[0]["choice"] == "skip"
  assert load_summary()["green_months"] == 1
