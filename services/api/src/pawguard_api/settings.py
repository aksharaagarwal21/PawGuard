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
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
