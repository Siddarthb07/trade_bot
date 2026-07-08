#!/usr/bin/env python3
"""Create or list WhatsApp groups for alert delivery."""

from __future__ import annotations

import argparse
import json
import sys

from core.config import get_settings
from notifier.waha import create_alert_group, list_group_chats, waha_healthy


def main() -> None:
  parser = argparse.ArgumentParser(description="Setup WhatsApp alert group")
  parser.add_argument("--list", action="store_true", help="List existing group chats")
  parser.add_argument("--create", action="store_true", help="Create Trade Bot Alerts group")
  parser.add_argument("--name", default="Trade Bot Alerts", help="Group name")
  parser.add_argument("--phone", default="", help="E.164 phone to add (e.g. 91XXXXXXXXXX); defaults to WHATSAPP_TO in .env")
  args = parser.parse_args()
  settings = get_settings()

  if not waha_healthy():
    print("WAHA session not healthy. Link WhatsApp first.", file=sys.stderr)
    sys.exit(1)

  if args.list:
    groups = list_group_chats()
    print(json.dumps(groups, indent=2, default=str))
    return

  if args.create:
    phone = args.phone or settings.whatsapp_to
    if not phone:
      print("Pass --phone or set WHATSAPP_TO in .env", file=sys.stderr)
      sys.exit(1)
    result = create_alert_group(args.name, phone)
    if not result:
      sys.exit(1)
    gid = result.get("id") or result.get("gid") or result.get("chatId")
    print(json.dumps(result, indent=2, default=str))
    print(f"\nAdd to .env:\nWHATSAPP_GROUP_ID={gid}")
    return

  parser.print_help()


if __name__ == "__main__":
  main()
