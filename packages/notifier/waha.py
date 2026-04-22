"""WhatsApp WAHA client — sends to group chat when configured."""

from __future__ import annotations

import logging

import httpx

from core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def resolve_chat_id() -> str | None:
  """Prefer dedicated group (@g.us) over personal DM (@c.us)."""
  group = (settings.whatsapp_group_id or "").strip()
  if group:
    if "@" not in group:
      return f"{group}@g.us"
    return group
  personal = (settings.whatsapp_to or "").strip()
  if not personal:
    return None
  if "@" not in personal:
    return f"{personal}@c.us"
  return personal


def waha_healthy() -> bool:
  try:
    with httpx.Client(timeout=10.0) as client:
      headers = {"X-Api-Key": settings.waha_api_key} if settings.waha_api_key else {}
      response = client.get(f"{settings.waha_base_url}/api/sessions/{settings.waha_session}", headers=headers)
      if response.status_code != 200:
        return False
      data = response.json()
      return data.get("status") in ("WORKING", "STARTING", "SCAN_QR_CODE")
  except Exception as exc:
    logger.warning("WAHA health check failed: %s", exc)
    return False


def send_whatsapp(text: str, chat_id: str | None = None) -> bool:
  if settings.notify_dry_run:
    logger.info("DRY RUN WhatsApp [%s]: %s", chat_id or resolve_chat_id(), text[:120])
    return True
  target = chat_id or resolve_chat_id()
  if not target:
    logger.warning("No WHATSAPP_GROUP_ID or WHATSAPP_TO configured")
    return False
  payload = {
    "session": settings.waha_session,
    "chatId": target,
    "text": text,
  }
  headers = {"X-Api-Key": settings.waha_api_key} if settings.waha_api_key else {}
  try:
    with httpx.Client(timeout=30.0) as client:
      response = client.post(
        f"{settings.waha_base_url}/api/sendText",
        json=payload,
        headers=headers,
      )
      response.raise_for_status()
      return True
  except Exception as exc:
    logger.exception("WAHA send failed: %s", exc)
    return False


def list_group_chats() -> list[dict]:
  headers = {"X-Api-Key": settings.waha_api_key} if settings.waha_api_key else {}
  with httpx.Client(timeout=30.0) as client:
    response = client.get(
      f"{settings.waha_base_url}/api/{settings.waha_session}/chats",
      headers=headers,
    )
    response.raise_for_status()
    chats = response.json()
  return [c for c in chats if str(c.get("id", "")).endswith("@g.us")]


def create_alert_group(name: str, participant_phone: str) -> dict | None:
  """Create a WhatsApp group and return chat metadata."""
  phone = participant_phone.strip().replace("+", "")
  if "@" not in phone:
    phone = f"{phone}@c.us"
  headers = {"X-Api-Key": settings.waha_api_key} if settings.waha_api_key else {}
  payload = {"name": name, "participants": [phone]}
  with httpx.Client(timeout=60.0) as client:
    response = client.post(
      f"{settings.waha_base_url}/api/{settings.waha_session}/groups",
      json=payload,
      headers=headers,
    )
    if response.status_code >= 400:
      logger.error("Create group failed: %s %s", response.status_code, response.text)
      return None
    return response.json()
