"""Ticker normalization tests."""

from core.tickers import normalize_entity, normalize_ticker


def test_normalize_entity():
  assert normalize_entity("  Reliance  Ltd. ") == "RELIANCE LTD"


def test_normalize_ticker_in():
  assert normalize_ticker("reliance", "IN") == "RELIANCE.NS"


def test_normalize_ticker_us():
  assert normalize_ticker("aapl", "US") == "AAPL"
