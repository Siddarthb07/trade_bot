"""Recognition stack: L0–L4 + deterministic NSE swarm (no LLM on fire path)."""

from __future__ import annotations

from processor.hybrid.recognition.stack import recognize_session
from processor.hybrid.recognition.types import RecognitionSnapshot

__all__ = ["recognize_session", "RecognitionSnapshot"]
