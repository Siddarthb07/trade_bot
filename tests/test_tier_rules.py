"""Message template tests."""

from datetime import datetime, timezone
from uuid import uuid4

from core.models import Signal, SignalScore
from notifier.templates import brief_whatsapp_message


def test_brief_message_length():
  signal = Signal(
    id=uuid4(),
    source="nse_bulk",
    source_ref="x",
    market="IN",
    entity="TEST ENTITY",
    entity_normalized="TEST ENTITY",
    ticker="RELIANCE",
    ticker_normalized="RELIANCE.NS",
    action="BUY",
    qty=1000,
    value=2.1e7,
    disclosed_at=datetime.now(timezone.utc),
  )
  score = SignalScore(signal_id=signal.id, tier="HIGH", historical_win_rate=0.61, n_trades=143)
  text = brief_whatsapp_message(signal, score, "http://192.168.1.42:3000")
  assert len(text) <= 200
  assert "RELIANCE" in text
