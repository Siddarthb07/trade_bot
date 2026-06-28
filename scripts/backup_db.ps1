# Backup Postgres database to user profile folder
param(
  [string]$BackupDir = "$env:USERPROFILE\smartmoney-backups"
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outFile = Join-Path $BackupDir "smartmoney-$timestamp.sql"

docker compose exec -T postgres pg_dump -U smartmoney smartmoney > $outFile
Write-Host "Backup written to $outFile"
