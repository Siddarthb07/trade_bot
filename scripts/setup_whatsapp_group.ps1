# Requires WAHA linked. Creates a dedicated WhatsApp GROUP (not self-DM).
# Usage:
#   docker compose exec processor python /app/scripts/setup_whatsapp_group.py --list
#   docker compose exec processor python /app/scripts/setup_whatsapp_group.py --create --phone 919606754584

param(
  [switch]$List,
  [switch]$Create,
  [string]$Phone = "919606754584"
)

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if ($List) {
  docker compose exec -T processor python /app/scripts/setup_whatsapp_group.py --list
  exit $LASTEXITCODE
}

if ($Create) {
  docker compose exec -T processor python /app/scripts/setup_whatsapp_group.py --create --phone $Phone
  exit $LASTEXITCODE
}

Write-Host @"
Trade Bot WhatsApp Group Setup
================================
1. Create a WhatsApp group manually on your phone named 'Trade Bot Alerts'
2. Add your linked number to it (or create via --Create below)
3. List groups to get the group ID:
   .\scripts\setup_whatsapp_group.ps1 -List
4. Set WHATSAPP_GROUP_ID=<id>@g.us in .env
5. Restart: docker compose up -d worker

Alerts go to the GROUP chat, not your personal DM.
Instant spam is OFF by default; daily picks at 7:30 PM IST.
"@
