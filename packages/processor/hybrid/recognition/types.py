"""Typed messages for the Godfather recognition swarm."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Ecology = Literal["nse", "crypto", "meme"]
DetectorStatus = Literal["ok", "insufficient_data", "missing", "cold_start"]


@dataclass(frozen=True)
class SessionGeometry:
  overnight_gap_pct: float | None = None
  or_width_pct: float | None = None
  ghlz_r1: float | None = None
  rv_1d: float | None = None
  rv_5d: float | None = None
  cross_section_residual: float | None = None
  btc_overnight_pct: float | None = None
  status: DetectorStatus = "ok"
  notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegimePosterior:
  p_trend: float = 0.0
  p_chop: float = 0.0
  p_risk_off: float = 0.0
  label: str = "unknown"
  hurst: float | None = None
  jump_day: bool = False
  break_prob: float = 0.0
  regime_age: int = 0
  status: DetectorStatus = "ok"


@dataclass(frozen=True)
class AgentMessage:
  agent: str
  vote: Literal["take", "skip", "annotate"] = "annotate"
  weight: float = 1.0
  reason: str = ""
  payload: dict[str, Any] = field(default_factory=dict)
  status: DetectorStatus = "ok"


@dataclass(frozen=True)
class Agreement:
  score: float = 0.0
  tradeable: bool = False
  collapsed_votes: int = 0
  raw_skip_votes: int = 0
  tau: float = 0.6
  reason: str = ""


@dataclass(frozen=True)
class Allocation:
  size_mult: float = 1.0
  expert: str = "cash"
  kelly_frac: float | None = None
  vol_scale: float | None = None
  notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecognitionSnapshot:
  ecology: Ecology = "nse"
  asof: str = ""
  geometry: SessionGeometry = field(default_factory=SessionGeometry)
  regime: RegimePosterior = field(default_factory=RegimePosterior)
  messages: tuple[AgentMessage, ...] = ()
  agreement: Agreement = field(default_factory=Agreement)
  allocation: Allocation = field(default_factory=Allocation)
  primary_side: str | None = None
  meta_p_take: float | None = None
  project: str = "godfather"

  def to_dict(self) -> dict[str, Any]:
    return asdict(self)
