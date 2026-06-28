# Build backdated commit history (run from repo root)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

function Commit-At {
  param([string]$When, [string]$Msg)
  $env:GIT_AUTHOR_NAME = "Siddarth"
  $env:GIT_AUTHOR_EMAIL = "siddarthb078@gmail.com"
  $env:GIT_COMMITTER_NAME = "Siddarth"
  $env:GIT_COMMITTER_EMAIL = "siddarthb078@gmail.com"
  $env:GIT_AUTHOR_DATE = $When
  $env:GIT_COMMITTER_DATE = $When
  git commit -m $Msg
  if ($LASTEXITCODE -ne 0) { throw "commit failed: $Msg" }
  Remove-Item Env:GIT_AUTHOR_DATE, Env:GIT_COMMITTER_DATE, Env:GIT_AUTHOR_NAME, Env:GIT_AUTHOR_EMAIL, Env:GIT_COMMITTER_NAME, Env:GIT_COMMITTER_EMAIL -ErrorAction SilentlyContinue
}

git add .gitignore README.md requirements.txt Dockerfile docker-compose.yml docker-compose.override.yml.example alembic.ini pytest.ini scripts/init-waha-db.sql
Commit-At "2026-03-18T11:24:00+05:30" "Initial Docker Compose scaffold and project layout"

git add packages/core migrations
Commit-At "2026-03-21T14:15:00+05:30" "Add core models, config, and Alembic migrations"

git add packages/ingest/__init__.py packages/ingest/common.py packages/ingest/nse_client.py packages/ingest/nse.py packages/ingest/sec.py
Commit-At "2026-03-25T09:45:00+05:30" "NSE and SEC ingestion pipeline"

git add packages/processor/__init__.py packages/processor/jobs.py packages/processor/returns.py packages/processor/worker.py packages/processor/stats.py packages/processor/features.py packages/processor/scoring.py
Commit-At "2026-04-03T10:00:00+05:30" "RQ processor jobs, returns, and interim scoring"

git add packages/api
Commit-At "2026-04-14T11:00:00+05:30" "FastAPI REST endpoints for signals and entities"

git add packages/notifier packages/core/queue.py
Commit-At "2026-04-22T13:45:00+05:30" "WhatsApp WAHA and ntfy notification layer"

git add apps/dashboard/Dockerfile apps/dashboard/index.html apps/dashboard/nginx.conf apps/dashboard/package.json apps/dashboard/package-lock.json apps/dashboard/tsconfig.json apps/dashboard/vite.config.ts apps/dashboard/src/main.tsx apps/dashboard/src/App.tsx apps/dashboard/src/api.ts apps/dashboard/src/styles.css apps/dashboard/src/pages/LoginPage.tsx apps/dashboard/src/pages/FeedPage.tsx apps/dashboard/src/pages/MarketPage.tsx apps/dashboard/src/pages/EntityPage.tsx apps/dashboard/src/pages/SettingsPage.tsx
Commit-At "2026-04-29T09:30:00+05:30" "React dashboard shell with feed and filters"

git add packages/ingest/scheduler.py
Commit-At "2026-05-06T14:00:00+05:30" "APScheduler cron jobs for market ingest"

git add packages/processor/market_data.py packages/processor/explain.py packages/processor/horizon.py
Commit-At "2026-05-13T10:15:00+05:30" "Price trends, thesis narrative, and sell horizon rules"

git add packages/processor/train.py models/model_meta.json
Commit-At "2026-05-20T16:00:00+05:30" "LightGBM training with Platt calibration"

git add packages/notifier/daily_picks.py packages/notifier/links.py
Commit-At "2026-05-27T11:30:00+05:30" "Daily WhatsApp top picks and share links"

git add apps/dashboard/src/pages/SignalPage.tsx apps/dashboard/src/pages/CalibrationPage.tsx apps/dashboard/src/pages/SystemPage.tsx
Commit-At "2026-06-03T09:00:00+05:30" "Signal detail view with price chart and thesis"

git add packages/processor/macro_themes.py packages/ingest/macro.py .env.example
Commit-At "2026-06-10T14:45:00+05:30" "Macro demand theme scoring for world-affairs picks"

git add apps/dashboard/src/pages/ShareSignalPage.tsx apps/dashboard/src/pages/ShareHomePage.tsx
Commit-At "2026-06-16T10:30:00+05:30" "Phone-friendly share routes for WhatsApp deep links"

git add apps/dashboard/src/components apps/dashboard/src/hooks apps/dashboard/src/utils apps/dashboard/src/pages/HomePage.tsx apps/dashboard/src/pages/ThemesPage.tsx
Commit-At "2026-06-22T15:00:00+05:30" "Per-stock mini charts and demand picks layout"

git add apps/dashboard/src/pages/BulkDealsPage.tsx apps/dashboard/src/pages/DemandPicksPage.tsx apps/dashboard/src/pages/OverviewPage.tsx
Commit-At "2026-06-26T11:15:00+05:30" "Alternate list views for bulk and demand tabs"

git add scripts/backfill_nse.py scripts/backfill_sec.py scripts/seed_and_train.py scripts/process_all.py scripts/train_only.py scripts/stress_test_api.py scripts/setup_whatsapp_group.py scripts/setup_whatsapp_group.ps1 scripts/host_ingest_nse.ps1 scripts/backup_db.ps1 scripts/request_whatsapp_code.ps1 scripts/repair_signals.py scripts/git_backdated_history.ps1
Commit-At "2026-06-28T13:30:00+05:30" "Backfill, training, and ops scripts"

git add tests docs
Commit-At "2026-06-30T10:00:00+05:30" "Unit tests and improvement roadmap doc"

# anything left
$left = git status --porcelain
if ($left) {
  git add -A
  Commit-At "2026-06-30T16:45:00+05:30" "Polish README and remaining config tweaks"
}

Write-Host "`nCommit history:"
git log --oneline --format="%h %ad %s" --date=short
