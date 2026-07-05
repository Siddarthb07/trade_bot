"""ML training gate unit tests."""

from processor.train import training_allowed


def test_gate_rejects_low_positive_rate():
  assert training_allowed(0.0, min_rate=0.05) is False
  assert training_allowed(0.04, min_rate=0.05) is False


def test_gate_accepts_sufficient_positive_rate():
  assert training_allowed(0.05, min_rate=0.05) is True
  assert training_allowed(0.12, min_rate=0.05) is True
