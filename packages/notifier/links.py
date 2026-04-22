"""Build shareable dashboard URLs for WhatsApp (phone-friendly).

WhatsApp often linkifies only the IP when URLs contain :port or ?query.
Use port 80 (no port in URL) and path-based tokens: /s/{id}/{token}
"""

from __future__ import annotations

from core.config import get_settings


def _root(base_url: str | None = None) -> str:
  settings = get_settings()
  url = (base_url or settings.dashboard_public_url).rstrip("/")
  # Strip :3000 etc. — LAN links should use port 80 for WhatsApp tap-to-open
  if url.endswith(":3000"):
    url = url[:-5]
  return url


def signal_dashboard_url(signal_id: str, base_url: str | None = None) -> str:
  settings = get_settings()
  root = _root(base_url)
  token = (settings.dashboard_share_token or "").strip()
  if token:
    return f"{root}/s/{signal_id}/{token}"
  return f"{root}/signals/{signal_id}"


def dashboard_home_url(base_url: str | None = None) -> str:
  settings = get_settings()
  root = _root(base_url)
  token = (settings.dashboard_share_token or "").strip()
  if token:
    return f"{root}/h/{token}"
  return root
