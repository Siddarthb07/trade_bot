"""Build shareable dashboard URLs for WhatsApp (phone-friendly).

WhatsApp on Android often linkifies only the IP (or treats it as a phone number),
dropping the path. Fixes:
  1. sslip.io hostname — http://192.168.1.42/x → http://192-168-1-42.sslip.io/x
  2. No :port in URL (use port 80)
  3. Query fallback — http://host/?s={id}&k={token} (when path links fail)
  4. URL on its own line at column 0 in templates
"""

from __future__ import annotations

import re
from urllib.parse import quote, urlparse, urlunparse

from core.config import get_settings

_IPV4 = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


def _ip_to_sslip_host(host: str) -> str:
  m = _IPV4.match(host.strip())
  if not m:
    return host
  return f"{m.group(1)}-{m.group(2)}-{m.group(3)}-{m.group(4)}.sslip.io"


def _root(base_url: str | None = None) -> str:
  settings = get_settings()
  url = (base_url or settings.dashboard_public_url).rstrip("/")
  if url.endswith(":3000"):
    url = url[:-5]
  return url


def to_whatsapp_friendly_url(url: str) -> str:
  """Make LAN URLs tappable in WhatsApp (sslip.io for raw IPv4 hosts)."""
  settings = get_settings()
  mode = (settings.whatsapp_link_mode or "sslip").lower()
  parsed = urlparse(url)
  host = parsed.hostname or ""
  port = parsed.port

  if mode == "plain":
    netloc = host
    if port and port not in (80, 443):
      netloc = f"{host}:{port}"
    return urlunparse(parsed._replace(netloc=netloc))

  if mode == "sslip" and _IPV4.match(host):
    host = _ip_to_sslip_host(host)
    port = None  # sslip links should not include :80

  netloc = host
  if port and port not in (80, 443):
    netloc = f"{host}:{port}"
  return urlunparse(parsed._replace(netloc=netloc, scheme=parsed.scheme or "http"))


def signal_dashboard_url(signal_id: str, base_url: str | None = None) -> str:
  settings = get_settings()
  root = to_whatsapp_friendly_url(_root(base_url))
  token = (settings.dashboard_share_token or "").strip()
  mode = (settings.whatsapp_link_mode or "sslip").lower()

  if token and mode == "query":
    return f"{root}/open?s={quote(signal_id, safe='')}&k={quote(token, safe='')}"

  if token:
    return f"{root}/s/{signal_id}/{token}"
  return f"{root}/signals/{signal_id}"


def dashboard_home_url(base_url: str | None = None) -> str:
  settings = get_settings()
  root = to_whatsapp_friendly_url(_root(base_url))
  token = (settings.dashboard_share_token or "").strip()
  mode = (settings.whatsapp_link_mode or "sslip").lower()

  if token and mode == "query":
    return f"{root}/open?k={quote(token, safe='')}"

  if token:
    return f"{root}/h/{token}"
  return root
