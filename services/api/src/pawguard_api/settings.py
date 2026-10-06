"""Runtime configuration. Every value is read from the environment (prefix ``PAWGUARD_``); see ``.env.example``."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]


def find_env_file() -> Path | None:
    """`PAWGUARD_ENV_FILE`, else the nearest `.env` walking up from the working directory. Containers set
    real environment variables instead and have no file."""
    explicit = os.environ.get("PAWGUARD_ENV_FILE")
    if explicit:
        return Path(explicit)
    for directory in (Path.cwd(), *Path.cwd().parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PAWGUARD_", env_file=find_env_file(), extra="ignore")

    env: Environment = "development"
    # Demo mode shows the DEMO banner, enables seeded-account shortcuts and the demo tenant.
    # It is refused outright in production (see validator below).
    demo_mode: bool = False
    log_level: str = "INFO"

    # Request-path database role (NOBYPASSRLS, not owner). Never the migration/owner credentials.
    database_url: str
    worker_database_url: str | None = None
    # Owner credentials: only used by Alembic and the admin CLI, never by request handlers.
    migrate_database_url: str | None = None
    db_pool_size: int = 10

    # Supabase: internal URL used by the API/worker; public URL is what browsers can reach.
    supabase_url: str
    supabase_public_url: str | None = None
    # True: hand browsers same-origin storage links (/storage/v1/object/...), which the web app forwards to Supabase.
    # Used when the app is reached through a public address (e.g. a tunnel) that cannot reach Supabase directly.
    storage_same_origin: bool = False
    supabase_secret_key: SecretStr | None = None
    storage_bucket: str = "pawguard-media"

    auth_issuer: str | None = None
    auth_audience: str = "authenticated"
    auth_jwks_url: str | None = None
    auth_leeway_seconds: int = 30

    redis_url: str = "redis://127.0.0.1:6379/0"

    # Directory holding registered model artefacts (verified against model_versions.sha256 before use).
    model_dir: str = "models"

    # Optional providers; absence keeps the feature visibly unavailable rather than faked.
    map_tile_url: str | None = None
    map_tile_attribution: str | None = None

    # Public web address used in links inside messages (the first extra origin wins: the public tunnel).
    web_origin: str = "http://localhost:3000"
    extra_web_origins: str = ""

    # Free notification providers (docs/FREE_SERVICES_SETUP.md). Demo organisations send only to these test
    # recipients, never to the fictional demo addresses.
    demo_notify_email: str | None = None
    demo_notify_whatsapp: str | None = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None
    email_daily_cap: int = 100
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_contact: str | None = None
    whatsapp_token: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_app_secret: str | None = None
    whatsapp_verify_token: str | None = None
    whatsapp_template: str | None = None
    whatsapp_api_version: str = "v26.0"  # Graph API; v26.0 introduced 29 July 2026
    llm_provider: str = "off"
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b"
    # Certificate OCR: tesseract (local, eng+hin+tam) | gemini (demo organisations only) | off.
    ocr_engine: str = "tesseract"
    tesseract_cmd: str | None = None
    tessdata_dir: str | None = None

    @model_validator(mode="after")
    def _defaults_and_guards(self) -> "Settings":
        base = self.supabase_url.rstrip("/")
        if self.auth_issuer is None:
            self.auth_issuer = f"{base}/auth/v1"
        if self.auth_jwks_url is None:
            self.auth_jwks_url = f"{base}/auth/v1/.well-known/jwks.json"
        if self.supabase_public_url is None:
            self.supabase_public_url = base
        if self.env == "production" and self.demo_mode:
            raise ValueError("PAWGUARD_DEMO_MODE must not be enabled in production")
        return self

    @property
    def public_app_url(self) -> str:
        extra = [o.strip() for o in self.extra_web_origins.split(",") if o.strip()]
        return (extra[0] if extra else self.web_origin).rstrip("/")

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
