"""NSE bulk/block smart-money gate for day-sim confluence and copy-pro.

Uses raw SQL so Python 3.9 can query without SQLAlchemy Mapped[| None] eval issues.
No lookahead: deals must be disclosed strictly before the session date.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text

from core.config import get_settings

BULK_SOURCES = ("nse_bulk", "nse_block", "bse_bulk")
BUY_ACTIONS = ("BUY", "P", "A")
IST = ZoneInfo("Asia/Kolkata")

_engine = None


def _eng():
  global _engine
  if _engine is None:
    import os

    url = get_settings().postgres_url
    # Host scripts talk to published port (compose maps 5433→5432).
    # Inside Compose, keep the service hostname — rewriting breaks Docker.
    in_docker = os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER") == "1"
    if "@postgres:" in url and not in_docker:
      url = url.replace("@postgres:5432", "@127.0.0.1:5433")
    _engine = create_engine(url, pool_pre_ping=True)
  return _engine


def _asof_start(asof: str) -> datetime:
  d = date.fromisoformat(asof[:10])
  return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def prior_session_window(asof: str, lookback_sessions: int = 1) -> tuple[datetime, datetime]:
  """Inclusive start / exclusive end for deals whose IST *deal date* is a prior weekday.

  NSE bulk rows store disclosed_at as deal-DATE 00:00 Asia/Kolkata → UTC.
  Ranking must use prior IST session(s) only — never the asof IST calendar day
  (same-day admission was a lookahead bug under the old UTC-midnight window).

  lookback_sessions=1 on Mon → Friday deal dates only (Sat/Sun stamps still map to Fri IST date).
  """
  asof_d = date.fromisoformat(asof[:10])
  n = max(1, int(lookback_sessions))
  # Walk back calendar days until we have N weekdays strictly before asof.
  d = asof_d - timedelta(days=1)
  prior_days: list[date] = []
  for _ in range(21):
    if d.weekday() < 5:
      prior_days.append(d)
      if len(prior_days) >= n:
        break
    d -= timedelta(days=1)
  if not prior_days:
    prior_days = [asof_d - timedelta(days=1)]
  start_day = prior_days[-1]  # oldest of the prior N weekdays
  # IST midnight of start_day → UTC; exclusive end = IST midnight of asof (excludes asof deal date)
  start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=IST).astimezone(timezone.utc)
  end = datetime(asof_d.year, asof_d.month, asof_d.day, tzinfo=IST).astimezone(timezone.utc)
  return start, end


def shrunk_win_rate(wr: float, n_trades: int, *, prior: float = 0.55, pseudo_n: float = 5.0) -> float:
  """Bayes-shrink raw investor WR toward prior — kills WR=1.0 on n=2 monopolies."""
  n = max(0, int(n_trades))
  k = max(0.0, float(pseudo_n))
  if k <= 0:
    return float(wr)
  return (float(wr) * n + float(prior) * k) / (n + k)


def empty_copy_pro_cooldown() -> dict[str, Any]:
  return {"tickers": {}, "entities": {}, "sitout": 0}


def tick_copy_pro_cooldown(state: dict[str, Any] | None) -> dict[str, Any]:
  """Decrement cooldown counters by one session."""
  st = state or empty_copy_pro_cooldown()
  out: dict[str, Any] = {"tickers": {}, "entities": {}, "sitout": 0}
  for key in ("tickers", "entities"):
    for name, left in (st.get(key) or {}).items():
      n = int(left) - 1
      if n > 0:
        out[key][str(name)] = n
  sit = int(st.get("sitout") or 0) - 1
  out["sitout"] = max(0, sit)
  return out


def register_copy_pro_outcomes(
  state: dict[str, Any] | None,
  trades: list[dict[str, Any]],
  *,
  ticker_cooldown_days: int = 1,
  entity_cooldown_days: int = 1,
  sitout_after_sl_days: int = 0,
) -> dict[str, Any]:
  """After a session: put SL'd tickers/entities on cooldown (and always tick down)."""
  st = tick_copy_pro_cooldown(state)
  td = max(0, int(ticker_cooldown_days))
  ed = max(0, int(entity_cooldown_days))
  sd = max(0, int(sitout_after_sl_days))
  hit_sl = False
  for t in trades or []:
    exit_reason = str(t.get("exit_reason") or t.get("exit") or "")
    if exit_reason != "stop_loss":
      continue
    hit_sl = True
    tk = str(t.get("ticker") or "").upper().strip()
    if tk and td > 0:
      st["tickers"][tk] = max(int(st["tickers"].get(tk, 0)), td)
      bare = tk.replace(".NS", "")
      st["tickers"][bare] = max(int(st["tickers"].get(bare, 0)), td)
    ent = str(t.get("bulk_entity") or t.get("entity_normalized") or "").strip()
    if not ent:
      meta = t.get("bulk_meta") if isinstance(t.get("bulk_meta"), dict) else {}
      ent = str(meta.get("entity_normalized") or "").strip()
    if ent and ed > 0:
      st["entities"][ent] = max(int(st["entities"].get(ent, 0)), ed)
  if hit_sl and sd > 0:
    st["sitout"] = max(int(st.get("sitout") or 0), sd)
  return st


def cooldown_excludes(state: dict[str, Any] | None) -> tuple[list[str], list[str]]:
  st = state or empty_copy_pro_cooldown()
  tickers = [k for k, v in (st.get("tickers") or {}).items() if int(v) > 0]
  entities = [k for k, v in (st.get("entities") or {}).items() if int(v) > 0]
  return tickers, entities


def copy_pro_should_sitout(state: dict[str, Any] | None) -> bool:
  return int((state or {}).get("sitout") or 0) > 0


def bulk_data_coverage(*, since: str = "2026-07-01") -> dict[str, Any]:
  """Return count + date range for bulk BUY signals (for DATA_GAP detection)."""
  try:
    with _eng().connect() as c:
      n = c.execute(
        text(
          "SELECT count(*) FROM signals WHERE source = ANY(:sources) "
          "AND action = ANY(:actions)"
        ),
        {"sources": list(BULK_SOURCES), "actions": list(BUY_ACTIONS)},
      ).scalar()
      r = c.execute(
        text(
          "SELECT min(disclosed_at), max(disclosed_at) FROM signals "
          "WHERE source = ANY(:sources) AND action = ANY(:actions) "
          "AND disclosed_at >= :since"
        ),
        {
          "sources": list(BULK_SOURCES),
          "actions": list(BUY_ACTIONS),
          "since": since,
        },
      ).one()
      n_win = c.execute(
        text(
          "SELECT count(*) FROM signals WHERE source = ANY(:sources) "
          "AND action = ANY(:actions) AND disclosed_at >= :since"
        ),
        {
          "sources": list(BULK_SOURCES),
          "actions": list(BUY_ACTIONS),
          "since": since,
        },
      ).scalar()
    return {
      "ok": True,
      "total_buys": int(n or 0),
      "window_buys": int(n_win or 0),
      "window_min": r[0].isoformat() if r and r[0] else None,
      "window_max": r[1].isoformat() if r and r[1] else None,
      "data_gap": int(n_win or 0) == 0,
    }
  except Exception as exc:  # noqa: BLE001 — bake-off must continue without DB
    return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "data_gap": True}


def ticker_has_pro_buy(
  ticker: str,
  asof: str,
  *,
  market: str = "IN",
  lookback_sessions: int = 3,
  min_win_rate: float = 0.55,
) -> dict[str, Any]:
  """True if ticker has a qualifying bulk BUY disclosed before asof within lookback.

  Investor win_rate from investor_stats; if no stat, deal still qualifies when
  min_win_rate <= 0 (else requires tracked WR >= min_win_rate).
  """
  start, end = prior_session_window(asof, lookback_sessions)
  t = ticker.upper().strip()
  variants = {t, t.replace(".NS", ""), t if t.endswith(".NS") else f"{t}.NS"}

  sql = text(
    """
    SELECT s.ticker, s.entity_normalized, s.value, s.disclosed_at, s.action, s.source,
           i.win_rate, i.n_trades
    FROM signals s
    LEFT JOIN investor_stats i
      ON i.entity_normalized = s.entity_normalized AND i.market = s.market
    WHERE s.market = :market
      AND s.source = ANY(:sources)
      AND s.action = ANY(:actions)
      AND s.disclosed_at >= :start
      AND s.disclosed_at < :end
      AND (upper(s.ticker) = ANY(:tickers) OR upper(s.ticker_normalized) = ANY(:tickers))
    ORDER BY s.disclosed_at DESC
    """
  )
  try:
    with _eng().connect() as c:
      rows = c.execute(
        sql,
        {
          "market": market.upper(),
          "sources": list(BULK_SOURCES),
          "actions": list(BUY_ACTIONS),
          "start": start,
          "end": end,
          "tickers": list(variants),
        },
      ).mappings().all()
  except Exception as exc:  # noqa: BLE001
    return {"ok": False, "passes": False, "error": str(exc), "deals": []}

  deals: list[dict[str, Any]] = []
  passes = False
  for row in rows:
    wr = row["win_rate"]
    deal = {
      "ticker": row["ticker"],
      "entity_normalized": row["entity_normalized"],
      "value": float(row["value"] or 0),
      "disclosed_at": row["disclosed_at"].isoformat() if row["disclosed_at"] else None,
      "win_rate": float(wr) if wr is not None else None,
      "n_trades": int(row["n_trades"] or 0),
      "source": row["source"],
    }
    deals.append(deal)
    if wr is None:
      # Untracked investor: allow only if threshold is disabled
      if min_win_rate <= 0:
        passes = True
    elif float(wr) >= min_win_rate:
      passes = True

  return {
    "ok": True,
    "passes": passes and bool(deals),
    "ticker": ticker,
    "asof": asof,
    "deals": deals[:8],
    "lookback_sessions": lookback_sessions,
    "min_win_rate": min_win_rate,
  }


def rank_pro_buys(
  asof: str,
  *,
  market: str = "IN",
  lookback_sessions: int = 1,
  min_win_rate: float = 0.55,
  min_n_trades: int = 2,
  min_deal_value: float = 25_000_000.0,
  limit: int = 8,
  universe: list[str] | None = None,
  exclude_tickers: list[str] | None = None,
  exclude_entities: list[str] | None = None,
  wr_prior: float = 0.55,
  wr_pseudo_n: float = 5.0,
) -> dict[str, Any]:
  """Rank tickers with pro bulk BUYs disclosed on prior session(s) before asof.

  lookback_sessions=1 → only the prior weekday session (weekend disclosures roll into Monday).
  Score uses Bayes-shrunk win_rate so WR=1.0 on n=2 cannot dominate giant-deal ranking.
  """
  import math

  start, end = prior_session_window(asof, lookback_sessions)
  # Deals only — WR is computed point-in-time below (not live investor_stats).
  sql = text(
    """
    SELECT s.ticker, s.ticker_normalized, s.entity_normalized, s.value, s.disclosed_at,
           s.source
    FROM signals s
    WHERE s.market = :market
      AND s.source = ANY(:sources)
      AND s.action = ANY(:actions)
      AND s.disclosed_at >= :start
      AND s.disclosed_at < :end
      AND COALESCE(s.value, 0) >= :min_val
    ORDER BY s.disclosed_at DESC
    """
  )
  try:
    with _eng().connect() as c:
      rows = c.execute(
        sql,
        {
          "market": market.upper(),
          "sources": list(BULK_SOURCES),
          "actions": list(BUY_ACTIONS),
          "start": start,
          "end": end,
          "min_val": float(min_deal_value),
        },
      ).mappings().all()
      # Preload entity forward returns for PIT WR (one query).
      ents = sorted({(r["entity_normalized"] or "").strip() for r in rows if r["entity_normalized"]})
      fr_by_ent: dict[str, list[tuple[datetime, float]]] = {e: [] for e in ents}
      if ents:
        fr_rows = c.execute(
          text(
            """
            SELECT s.entity_normalized, s.disclosed_at, fr.return_pct
            FROM signals s
            JOIN forward_returns fr ON fr.signal_id = s.id AND fr."window" = '3mo'
            WHERE s.market = :market
              AND s.entity_normalized = ANY(:ents)
              AND s.action = ANY(:actions)
              AND fr.return_pct IS NOT NULL
            """
          ),
          {"market": market.upper(), "ents": ents, "actions": list(BUY_ACTIONS)},
        ).mappings().all()
        for fr in fr_rows:
          ent = (fr["entity_normalized"] or "").strip()
          disc = fr["disclosed_at"]
          if disc is not None and disc.tzinfo is None:
            disc = disc.replace(tzinfo=timezone.utc)
          fr_by_ent.setdefault(ent, []).append((disc, float(fr["return_pct"])))
  except Exception as exc:  # noqa: BLE001
    return {"ok": False, "error": str(exc), "data_gap": True, "picks": []}

  asof_d = date.fromisoformat(asof[:10])

  def pit_wr(entity: str) -> tuple[float | None, int]:
    xs = []
    for disc, ret in fr_by_ent.get(entity, []):
      if disc is None:
        continue
      d0 = disc.astimezone(IST).date()
      if d0 + timedelta(days=90) < asof_d:
        xs.append(ret)
    if not xs:
      return None, 0
    wr = sum(1 for x in xs if x > 0) / len(xs)
    return wr, len(xs)

  uni = None
  if universe:
    uni = set()
    for t in universe:
      u = t.upper()
      uni.add(u)
      uni.add(u.replace(".NS", ""))
      uni.add(u if u.endswith(".NS") else f"{u}.NS")

  exclude: set[str] = set()
  if exclude_tickers:
    for t in exclude_tickers:
      u = t.upper().strip()
      exclude.add(u)
      exclude.add(u.replace(".NS", ""))
      exclude.add(u if u.endswith(".NS") else f"{u}.NS")

  exclude_ent = {e.strip().upper() for e in (exclude_entities or []) if e and str(e).strip()}

  best: dict[str, dict[str, Any]] = {}
  for row in rows:
    raw = (row["ticker"] or "").upper()
    norm = (row["ticker_normalized"] or raw).upper()
    key = raw if raw.endswith(".NS") else (f"{norm}.NS" if not norm.endswith(".NS") else norm)
    if key in exclude or raw in exclude or norm in exclude:
      continue
    ent = (row["entity_normalized"] or "").strip()
    if ent and ent.upper() in exclude_ent:
      continue
    if uni is not None and raw not in uni and norm not in uni and key not in uni:
      continue
    wr, n_tr = pit_wr(ent)
    if wr is None or n_tr < int(min_n_trades) or wr < float(min_win_rate):
      continue
    val = float(row["value"] or 0)
    wr_eff = shrunk_win_rate(wr, n_tr, prior=wr_prior, pseudo_n=wr_pseudo_n)
    score = wr_eff * math.log1p(max(val, 0.0)) * (1.0 + 0.2 * math.log1p(n_tr))
    prev = best.get(key)
    if prev is None or score > prev["score"]:
      best[key] = {
        "ticker": key,
        "score": round(score, 4),
        "win_rate": wr,
        "win_rate_eff": round(wr_eff, 4),
        "value": val,
        "entity_normalized": row["entity_normalized"],
        "disclosed_at": row["disclosed_at"].isoformat() if row["disclosed_at"] else None,
        "n_trades": n_tr,
        "source": row["source"],
        "wr_source": "pit_3mo_matured_before_asof",
      }

  picks = sorted(best.values(), key=lambda x: x["score"], reverse=True)[:limit]
  return {
    "ok": True,
    "data_gap": len(rows) == 0,
    "asof": asof,
    "n_raw_deals": len(rows),
    "window_start": start.isoformat(),
    "window_end": end.isoformat(),
    "picks": picks,
    "filters": {
      "min_win_rate": min_win_rate,
      "min_n_trades": min_n_trades,
      "min_deal_value": min_deal_value,
      "wr_prior": wr_prior,
      "wr_pseudo_n": wr_pseudo_n,
      "exclude_entities": list(exclude_ent),
      "wr_mode": "point_in_time",
    },
  }
