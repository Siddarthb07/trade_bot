"""ntfy fallback notifier."""

from __future__ import annotations

import logging

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def send_ntfy(text: str, title: str = "SmartMoney") -> bool:
  if settings.notify_dry_run:
    logger.info("DRY RUN ntfy: %s", text)
    return True
  try:
    with httpx.Client(timeout=15.0) as client:
      response = client.post(
        f"{settings.ntfy_server}/{settings.ntfy_topic}",
        data=text.encode("utf-8"),
        headers={"Title": title, "Priority": "high"},
      )
      response.raise_for_status()
      return True
  except Exception as exc:
    logger.exception("ntfy send failed: %s", exc)
    return False
