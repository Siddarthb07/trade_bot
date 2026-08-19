"""APScheduler worker entrypoint."""

from __future__ import annotations

import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo

from ingest.macro import ingest_macro_themes
from ingest.nse import ingest_nse_block_intraday, ingest_nse_eod
from ingest.pull_free import pull_all_free_data
from ingest.sec import ingest_13f, ingest_form4
from notifier.daily_picks import send_daily_picks
from notifier.digest import send_daily_digest
from notifier.exit_reminders import send_exit_reminders
from notifier.holdings import send_holdings_digest
from processor.forward_backfill import run_scheduled_forward_backfill
from processor.ml_jobs import run_scheduled_train

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


def run_scheduled_nse_historical_backfill() -> dict:
  from core.config import get_settings
  from ingest.nse import backfill_nse_historical

  settings = get_settings()
  return backfill_nse_historical(days=settings.ml_backfill_days)


def run_sentiment_ingest() -> dict:
  from processor.sentiment import ingest_sentiment_snapshot

  return ingest_sentiment_snapshot()


def run_in_flatten() -> dict:
  from broker.daytrade import run_in_day_flatten_if_due

  return run_in_day_flatten_if_due()


def run_us_flatten() -> dict:
  from broker.daytrade import run_us_day_flatten_if_due

  return run_us_day_flatten_if_due()


def run_seed_strategies() -> dict:
  from processor.ensemble import seed_strategy_candidates

  return {"seeded": seed_strategy_candidates()}


def main() -> None:
  scheduler = BlockingScheduler(timezone=IST)
  # Seed strategy registry once at start
  try:
    run_seed_strategies()
  except Exception as exc:
    logger.warning("Strategy seed failed: %s", exc)

  scheduler.add_job(ingest_nse_block_intraday, CronTrigger(hour=10, minute=35, timezone=IST), id="nse_block")
  scheduler.add_job(ingest_nse_eod, CronTrigger(hour=18, minute=15, timezone=IST), id="nse_eod")
  scheduler.add_job(pull_all_free_data, CronTrigger(hour=19, minute=0, timezone=IST), id="pull_free_data")
  scheduler.add_job(run_scheduled_forward_backfill, CronTrigger(hour=18, minute=35, timezone=IST), id="forward_backfill")
  scheduler.add_job(ingest_macro_themes, CronTrigger(hour=18, minute=45, timezone=IST), id="macro_themes")
  scheduler.add_job(send_exit_reminders, CronTrigger(hour="8,19", minute=0, timezone=IST), id="exit_reminders")
  scheduler.add_job(send_holdings_digest, CronTrigger(hour=8, minute=15, timezone=IST), id="holdings_digest", kwargs={"market": "IN"})
  scheduler.add_job(send_daily_picks, CronTrigger(hour=19, minute=30, timezone=IST), id="in_daily_picks", kwargs={"market": "IN"})
  scheduler.add_job(run_scheduled_nse_historical_backfill, CronTrigger(day_of_week="sat", hour=4, minute=0, timezone=IST), id="nse_historical_backfill")
  scheduler.add_job(run_scheduled_train, CronTrigger(day_of_week="sun", hour=5, minute=30, timezone=IST), id="ml_weekly_train")
  scheduler.add_job(ingest_form4, CronTrigger(hour="*/6"), id="sec_form4")
  scheduler.add_job(ingest_13f, CronTrigger(hour=7, minute=0, timezone=IST), id="sec_13f")
  scheduler.add_job(send_daily_digest, CronTrigger(hour=9, minute=0, timezone=IST), id="us_digest")
  # Autonomy: sentiment hourly, IN flatten near close, US flatten near US close (IST ~01:15 / 01:45 DST-ish)
  scheduler.add_job(run_sentiment_ingest, CronTrigger(minute=20), id="wsb_sentiment")
  scheduler.add_job(run_in_flatten, CronTrigger(hour=15, minute=16, timezone=IST), id="in_day_flatten")
  scheduler.add_job(run_us_flatten, CronTrigger(hour=1, minute=15, timezone=IST), id="us_day_flatten")

  def shutdown(_signum, _frame):
    logger.info("Shutting down scheduler")
    scheduler.shutdown(wait=False)
    sys.exit(0)

  signal.signal(signal.SIGINT, shutdown)
  signal.signal(signal.SIGTERM, shutdown)
  logger.info("Worker scheduler started")
  scheduler.start()


if __name__ == "__main__":
  main()
