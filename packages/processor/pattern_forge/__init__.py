"""Pattern Forge — candle + analog method family signals."""

from __future__ import annotations

from processor.pattern_forge.analogs import analog_signal, build_library_from_paths, find_analogs
from processor.pattern_forge.candles import candle_signal
from processor.pattern_forge.session import primary_signal, simulate_pattern_session

__all__ = [
  "candle_signal",
  "analog_signal",
  "find_analogs",
  "build_library_from_paths",
  "primary_signal",
  "simulate_pattern_session",
]
