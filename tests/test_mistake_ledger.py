"""Pattern Forge mistake ledger — anti-repeat learning."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.pattern_forge.mistake_ledger import (
  learn_from_day,
  read_briefing,
  reset_ledger,
)


def test_loss_bans_ticker_next_days(tmp_path, monkeypatch):
  import processor.pattern_forge.mistake_ledger as ml

  monkeypatch.setattr(ml, "RULES_PATH", tmp_path / "mistake_rules.json")
  monkeypatch.setattr(ml, "MISTAKES_PATH", tmp_path / "mistakes.jsonl")
  monkeypatch.setattr(ml, "HISTORY_PATH", tmp_path / "mistake_history.jsonl")
  monkeypatch.setattr(ml, "LEDGER_DIR", tmp_path)

  reset_ledger(keep_mistake_log=False)
  out = learn_from_day(
    asof="2025-06-02",
    trades=[{"ticker": "RELIANCE.NS", "pnl": -120.0, "pnl_pct": -1.2, "exit_reason": "next_close"}],
    day_pnl=-120.0,
    day_return_pct=-1.2,
  )
  assert "exclude_ticker::RELIANCE.NS" in out["rules_touched"]

  b = read_briefing("2025-06-03", mark_read=False)
  assert "RELIANCE.NS" in b["exclude_tickers"]
  assert b["size_mult"] <= 0.75  # soft red-day size-down


def test_two_red_days_sitout(tmp_path, monkeypatch):
  import processor.pattern_forge.mistake_ledger as ml

  monkeypatch.setattr(ml, "RULES_PATH", tmp_path / "mistake_rules.json")
  monkeypatch.setattr(ml, "MISTAKES_PATH", tmp_path / "mistakes.jsonl")
  monkeypatch.setattr(ml, "HISTORY_PATH", tmp_path / "mistake_history.jsonl")
  monkeypatch.setattr(ml, "LEDGER_DIR", tmp_path)

  reset_ledger(keep_mistake_log=False)
  for d, pnl in [("2025-06-02", -1.0), ("2025-06-03", -1.1), ("2025-06-04", -0.9)]:
    learn_from_day(
      asof=d,
      trades=[{"ticker": "A.NS", "pnl": -50.0, "pnl_pct": -1.0}],
      day_pnl=-50.0,
      day_return_pct=pnl,
    )
  b = read_briefing("2025-06-05", mark_read=False)
  assert b["sitout"] is True
