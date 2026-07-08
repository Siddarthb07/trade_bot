"""NSE free endpoints: FII/DII, announcements, bhavcopy."""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from core.db import SessionLocal
from ingest.common import finish_ingestion_run, start_ingestion_run
from ingest.nse_client import NSEClient
from ingest.snapshot_store import upsert_eod_prices, upsert_snapshot

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


def ingest_nse_fii_dii() -> dict:
    db = SessionLocal()
    run = start_ingestion_run(db, "ingest_nse_fii_dii")
    try:
        client = NSEClient()
        rows = client.fetch_fii_dii()
        as_of = datetime.now(timezone.utc)
        key = as_of.astimezone(IST).strftime("%Y-%m-%d")
        _, created = upsert_snapshot(
            db,
            source="nse_fii_dii",
            snapshot_key=key,
            as_of=as_of,
            market="IN",
            payload={"rows": rows, "count": len(rows)},
        )
        finish_ingestion_run(db, run, rows_in=len(rows), rows_new=1 if created else 0)
        return {"rows": len(rows), "snapshot_key": key, "created": created}
    except Exception as exc:
        finish_ingestion_run(db, run, rows_in=0, rows_new=0, status="failed", error=str(exc))
        raise
    finally:
        db.close()


def ingest_nse_announcements(days: int = 7) -> dict:
    db = SessionLocal()
    run = start_ingestion_run(db, "ingest_nse_announcements")
    try:
        client = NSEClient()
        end = datetime.now(IST)
        start = end - timedelta(days=days)
        rows = client.fetch_corp_announcements(start, end)
        as_of = datetime.now(timezone.utc)
        key = f"{start.strftime('%Y-%m-%d')}_{end.strftime('%Y-%m-%d')}"
        _, created = upsert_snapshot(
            db,
            source="nse_announcements",
            snapshot_key=key,
            as_of=as_of,
            market="IN",
            payload={"announcements": rows[:500], "total": len(rows)},
        )
        finish_ingestion_run(db, run, rows_in=len(rows), rows_new=1 if created else 0)
        return {"total": len(rows), "stored": min(len(rows), 500), "created": created}
    except Exception as exc:
        finish_ingestion_run(db, run, rows_in=0, rows_new=0, status="failed", error=str(exc))
        raise
    finally:
        db.close()


def ingest_nse_bhavcopy(max_lookback_days: int = 10) -> dict:
    db = SessionLocal()
    run = start_ingestion_run(db, "ingest_nse_bhavcopy")
    try:
        client = NSEClient()
        csv_text = None
        trade_dt = None
        for offset in range(max_lookback_days):
            candidate = datetime.now(IST) - timedelta(days=offset)
            if candidate.weekday() >= 5:
                continue
            csv_text = client.fetch_bhavcopy_csv(candidate)
            if csv_text:
                trade_dt = candidate.date()
                break
        if not csv_text or trade_dt is None:
            finish_ingestion_run(db, run, rows_in=0, rows_new=0, status="failed", error="No bhavcopy found")
            return {"error": "no bhavcopy", "inserted": 0}

        df = pd.read_csv(io.StringIO(csv_text))
        df.columns = [str(c).strip() for c in df.columns]
        sym_col = next((c for c in df.columns if c.upper() == "SYMBOL"), None)
        close_col = next((c for c in df.columns if "CLOSE" in c.upper()), None)
        vol_col = next((c for c in df.columns if "TOTTRDQTY" in c.upper() or c.upper() == "VOLUME"), None)
        if not sym_col or not close_col:
            raise RuntimeError(f"Unexpected bhavcopy columns: {list(df.columns)[:8]}")

        price_rows: list[dict] = []
        for _, row in df.iterrows():
            sym = str(row[sym_col]).strip()
            close = row[close_col]
            if not sym or sym.lower() == "nan" or pd.isna(close):
                continue
            vol = row[vol_col] if vol_col else None
            price_rows.append({
                "ticker": sym,
                "close": float(str(close).replace(",", "")),
                "volume": int(float(str(vol).replace(",", ""))) if vol_col and pd.notna(vol) else None,
            })

        inserted, skipped = upsert_eod_prices(
            db, price_rows, market="IN", trade_date=trade_dt, source="nse_bhavcopy"
        )
        upsert_snapshot(
            db,
            source="nse_bhavcopy",
            snapshot_key=str(trade_dt),
            as_of=datetime.now(timezone.utc),
            market="IN",
            payload={"trade_date": str(trade_dt), "symbols": len(price_rows), "inserted": inserted},
        )
        finish_ingestion_run(db, run, rows_in=len(price_rows), rows_new=inserted)
        return {"trade_date": str(trade_dt), "symbols": len(price_rows), "inserted": inserted, "skipped": skipped}
    except Exception as exc:
        finish_ingestion_run(db, run, rows_in=0, rows_new=0, status="failed", error=str(exc))
        raise
    finally:
        db.close()
