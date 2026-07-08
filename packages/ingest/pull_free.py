"""Pull all free public data sources."""

from __future__ import annotations

import logging
from typing import Any, Callable

from ingest.bse import ingest_bse_bulk
from ingest.fred import ingest_macro_free
from ingest.macro import ingest_macro_themes
from ingest.nse import ingest_nse_eod
from ingest.nse_free import ingest_nse_announcements, ingest_nse_bhavcopy, ingest_nse_fii_dii
from ingest.sec import ingest_13f, ingest_form4, ingest_sec_8k

logger = logging.getLogger(__name__)


def pull_all_free_data(*, bse_days: int = 7, announcement_days: int = 7) -> dict[str, Any]:
    """Run every free ingest job. Partial failures are logged; others continue."""
    results: dict[str, Any] = {}

    jobs: list[tuple[str, Callable[[], dict]]] = [
        ("nse_eod", ingest_nse_eod),
        ("nse_fii_dii", ingest_nse_fii_dii),
        ("nse_announcements", lambda: ingest_nse_announcements(days=announcement_days)),
        ("nse_bhavcopy", ingest_nse_bhavcopy),
        ("bse_bulk", lambda: ingest_bse_bulk(days=bse_days)),
        ("sec_form4", ingest_form4),
        ("sec_13f", ingest_13f),
        ("sec_8k", ingest_sec_8k),
        ("macro_themes", ingest_macro_themes),
        ("macro_free", ingest_macro_free),
    ]

    for name, fn in jobs:
        try:
            results[name] = fn()
            logger.info("pull_all_free_data %s: %s", name, results[name])
        except Exception as exc:
            logger.exception("pull_all_free_data %s failed", name)
            results[name] = {"error": str(exc)}

    ok = sum(1 for v in results.values() if "error" not in v)
    results["summary"] = {"ok": ok, "failed": len(jobs) - ok, "total_jobs": len(jobs)}
    return results
