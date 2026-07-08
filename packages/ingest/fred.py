"""FRED + World Bank free macro series."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

from core.config import get_settings
from core.db import SessionLocal
from ingest.common import finish_ingestion_run, start_ingestion_run
from ingest.snapshot_store import upsert_snapshot

logger = logging.getLogger(__name__)

# FRED series (free API key from https://fred.stlouisfed.org/docs/api/api_key.html)
FRED_SERIES = {
    "DGS10": "US 10Y Treasury yield",
    "DTWEXBGS": "USD broad index",
    "DCOILWTICO": "WTI crude oil",
    "VIXCLS": "VIX",
}

# World Bank — no key required
WB_SERIES = {
    "FP.WDI.COPP": ("IN", "Copper price proxy (WDI)"),
}


def _fetch_fred(series_id: str, api_key: str, limit: int = 30) -> list[dict]:
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    obs = resp.json().get("observations", [])
    return [{"date": o["date"], "value": o["value"]} for o in obs if o.get("value") not in (".", None, "")]


def _fetch_worldbank(indicator: str, country: str = "IN", limit: int = 10) -> list[dict]:
    url = f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
    params = {"format": "json", "per_page": limit, "date": "2015:2026"}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list) or len(data) < 2:
        return []
    rows = data[1] or []
    out = []
    for row in rows:
        if row.get("value") is None:
            continue
        out.append({"date": row.get("date"), "value": row.get("value")})
    return out


def ingest_macro_free() -> dict:
    settings = get_settings()
    db = SessionLocal()
    run = start_ingestion_run(db, "ingest_macro_free")
    results: dict = {"fred": {}, "world_bank": {}, "skipped": []}
    rows_in = 0
    try:
        api_key = getattr(settings, "fred_api_key", "") or ""
        as_of = datetime.now(timezone.utc)
        key_day = as_of.astimezone().strftime("%Y-%m-%d")

        if api_key:
            for series_id, label in FRED_SERIES.items():
                try:
                    obs = _fetch_fred(series_id, api_key)
                    rows_in += len(obs)
                    upsert_snapshot(
                        db,
                        source="fred",
                        snapshot_key=f"{series_id}:{key_day}",
                        as_of=as_of,
                        market="US",
                        payload={"series_id": series_id, "label": label, "observations": obs},
                    )
                    results["fred"][series_id] = len(obs)
                except Exception as exc:
                    logger.warning("FRED %s failed: %s", series_id, exc)
                    results["fred"][series_id] = f"error: {exc}"
        else:
            results["skipped"].append("fred (set FRED_API_KEY in .env — free at fred.stlouisfed.org)")

        for indicator, (country, label) in WB_SERIES.items():
            try:
                obs = _fetch_worldbank(indicator, country=country)
                rows_in += len(obs)
                upsert_snapshot(
                    db,
                    source="world_bank",
                    snapshot_key=f"{indicator}:{country}:{key_day}",
                    as_of=as_of,
                    market=country,
                    payload={"indicator": indicator, "label": label, "observations": obs},
                )
                results["world_bank"][indicator] = len(obs)
            except Exception as exc:
                logger.warning("World Bank %s failed: %s", indicator, exc)
                results["world_bank"][indicator] = f"error: {exc}"

        finish_ingestion_run(db, run, rows_in=rows_in, rows_new=len(results["fred"]) + len(results["world_bank"]))
        return results
    except Exception as exc:
        finish_ingestion_run(db, run, rows_in=rows_in, rows_new=0, status="failed", error=str(exc))
        raise
    finally:
        db.close()
