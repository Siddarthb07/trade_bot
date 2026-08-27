"""OR-width chase product configs — raw heroes + guarded paper-month variants."""

from __future__ import annotations

from processor.day_sim import ORWIDTH_GUARD_DEFAULTS

_HERO_BASE = {
  "filter_mode": "target_return",
  "max_leverage": 75.0,
  "conf_floor": 0.48,
  "min_or_pct": 0.0015,
  "exit_at_session_end": True,
  "rank_by": "or_width",
  "max_chase_attempts": 5,
  "bar_interval": "auto",
}

ORWIDTH_HERO_CONFIGS: dict[str, dict] = {
  "in_tr10_orwidth_chase5_75x": {
    **_HERO_BASE,
    "target_return_pct": 10.0,
  },
  "in_tr8_orwidth_chase5_75x": {
    **_HERO_BASE,
    "target_return_pct": 8.0,
  },
  "in_tr10_orwidth_chase5_75x_guard": {
    **_HERO_BASE,
    "target_return_pct": 10.0,
    **ORWIDTH_GUARD_DEFAULTS,
  },
  "in_tr8_orwidth_chase5_75x_guard": {
    **_HERO_BASE,
    "target_return_pct": 8.0,
    **ORWIDTH_GUARD_DEFAULTS,
  },
}

DEFAULT_PAPER_PRODUCT = "in_tr10_orwidth_chase5_75x_guard"


def product_kwargs(name: str | None = None) -> dict:
  key = (name or DEFAULT_PAPER_PRODUCT).strip()
  if key not in ORWIDTH_HERO_CONFIGS:
    raise KeyError(f"unknown orwidth product: {key}")
  return dict(ORWIDTH_HERO_CONFIGS[key])
