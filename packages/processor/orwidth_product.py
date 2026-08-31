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
  # Lane A bake-off: guarded ORB only when NSE bulk BUY confluence exists
  "in_tr10_orwidth_chase5_75x_guard_bulk": {
    **_HERO_BASE,
    "target_return_pct": 10.0,
    **ORWIDTH_GUARD_DEFAULTS,
    "require_bulk_confluence": True,
    "bulk_lookback_sessions": 3,
    "bulk_min_win_rate": 0.55,
  },
}

DEFAULT_PAPER_PRODUCT = "in_tr10_orwidth_chase5_75x_guard"
# Break-even bake-off (2026-08-29): Lane B copy_bulk_pro on July bulk window
# compound +5.39% with positive trade-day expectancy. Aug A/B DATA_GAP (bulk DB ends 2026-07-20).
PROMOTED_BAKEOFF_STRATEGY = "copy_bulk_pro"


def product_kwargs(name: str | None = None) -> dict:
  key = (name or DEFAULT_PAPER_PRODUCT).strip()
  if key not in ORWIDTH_HERO_CONFIGS:
    raise KeyError(f"unknown orwidth product: {key}")
  return dict(ORWIDTH_HERO_CONFIGS[key])
