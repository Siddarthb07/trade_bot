"""Tests for adaptive fingerprint learning (forward-safe, no calendar)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

from processor.pattern_forge.adaptive_learn import (
  MIN_FP_HITS_TO_SIZE,
  context_fingerprint,
  fingerprint_rule_from_failure,
  match_fingerprint_rules,
)


def test_fingerprint_stable_id():
  a = context_fingerprint(regime="trend", breadth_frac=0.4, ytd_underwater=True, loss_streak=2)
  b = context_fingerprint(regime="trend", breadth_frac=0.41, ytd_underwater=True, loss_streak=2)
  assert a["id"] == b["id"]
  assert "uw_1" in a["id"]
  assert "st_2" in a["id"]


def test_fingerprint_needs_evidence_before_size():
  fp = context_fingerprint(regime="risk_off", breadth_frac=0.2, ytd_underwater=True, loss_streak=3)
  r1 = fingerprint_rule_from_failure(fp=fp, asof="2024-01-02", day_return_pct=-2.0, expires_on="2024-01-12", prior_hits=0)
  assert r1["evidence_hits"] == 1
  assert r1["active_defense"] is False
  matched = match_fingerprint_rules([r1], fp=fp)
  assert matched["size_mult"] == 1.0
  assert matched["sitout"] is False

  r3 = fingerprint_rule_from_failure(
    fp=fp, asof="2024-01-10", day_return_pct=-1.5, expires_on="2024-01-22", prior_hits=MIN_FP_HITS_TO_SIZE - 1
  )
  assert r3["active_defense"] is True
  matched3 = match_fingerprint_rules([r3], fp=fp)
  assert matched3["size_mult"] < 1.0


def test_no_amplify():
  fp = context_fingerprint(regime="chop", breadth_frac=0.55, ytd_underwater=False, loss_streak=0)
  rule = fingerprint_rule_from_failure(fp=fp, asof="2024-03-01", day_return_pct=-1.0, expires_on="2024-03-12", prior_hits=5)
  m = match_fingerprint_rules([rule], fp=fp)
  assert m["size_mult"] <= 1.0
