"""Shared configuration."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_url: str = "postgresql://smartmoney:changeme@postgres:5432/smartmoney"
    redis_url: str = "redis://redis:6379/0"

    alerts_enabled: bool = False
    notify_dry_run: bool = False
    dashboard_public_url: str = "http://192.168.1.42:3000"
    whatsapp_to: str = ""
    ntfy_topic: str = "trade-bot-alerts"
    ntfy_server: str = "http://ntfy:80"

    waha_base_url: str = "http://waha:3000"
    waha_api_key: str = ""
    waha_session: str = "default"
    waha_dashboard_username: str = "admin"
    waha_dashboard_password: str = "changeme"

    sec_identity: str = "SmartMoney Tracker user@example.com"

    api_username: str = "admin"
    api_password: str = "changeme"
    internal_api_key: str = "host-fallback-key"

    win_threshold_pct: float = 0.0
    win_window: str = "3mo"
    tz: str = "Asia/Kolkata"

    backfill_min_signals: int = 50
    backfill_min_entities: int = 5
    backfill_min_entity_trades: int = 10

    # WhatsApp: prefer group chat (120363...@g.us) over personal DM
    whatsapp_group_id: str = ""
    # Instant per-signal alerts (off by default — use daily picks instead)
    alert_instant_enabled: bool = False
    alert_min_probability: float = 0.62
    alert_min_expected_return_pct: float = 0.06
    alert_min_deal_value_inr: float = 1e7
    alert_buys_only: bool = True
    alert_instant_min_tier: str = "HIGH"
    # Daily curated picks digest (primary WhatsApp channel)
    daily_picks_enabled: bool = True
    daily_picks_max: int = 5
    daily_picks_min_probability: float = 0.50
    daily_picks_min_expected_return_pct: float = 0.04
    # Token for phone links from WhatsApp (?k=...) — set in .env (generate with secrets.token_urlsafe(32))
    dashboard_share_token: str = ""
    # Macro / world-affairs theme picks
    macro_themes_enabled: bool = True
    macro_themes_max_signals: int = 30
    macro_themes_min_composite: float = 0.12
    macro_themes_whatsapp_max: int = 3
    macro_themes_min_probability: float = 0.52
    # Exit / review WhatsApp reminders (Phase 1)
    exit_reminders_enabled: bool = True
    # ML training (Phase 2)
    ml_train_enabled: bool = True
    ml_train_min_samples: int = 30
    ml_min_positive_rate: float = 0.05
    ml_train_markets: str = "IN"
    ml_train_sources: str = "nse_bulk,nse_block,bse_bulk"
    ml_backfill_days: int = 90
    bulk_confidence_boost: float = 0.05
    # Hold display (Phase 5)
    hold_display_mode: str = "both"  # days | weeks | both
    theme_hold_multiplier: float = 1.0
    min_hold_days_filter: int = 0
    # WhatsApp link format: sslip (IP→sslip.io), query (?s=&k=), or plain
    whatsapp_link_mode: str = "sslip"
    # Holdings digest (active hold window)
    holdings_whatsapp_max: int = 8
    holdings_digest_enabled: bool = True
    # Free macro APIs (optional — FRED key is free at fred.stlouisfed.org)
    fred_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
