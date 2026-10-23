"""Runtime configuration from environment variables.

For local development use `uvicorn app.main:app --env-file .env` (see .env.example).

Fails closed: ENV defaults to "production", and production refuses to start with a
missing/placeholder JWT secret, without an explicit CORS allow-list, or without
DATABASE_URL. Error messages never echo the offending value.
"""

import os
import secrets

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

DEV_ENVS = {"dev", "development", "test"}
MIN_SECRET_LEN = 32
PLACEHOLDER_SECRETS = {"change-me", "changeme", "your_jwt_secret_here", "secret"}


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    env: str = "production"
    jwt_secret: str = ""
    cors_origins: list[str] = []
    database_url: str = ""
    access_token_minutes: int = 12 * 60
    max_upload_mb: int = 100
    max_upload_bytes: int = 0  # derived from max_upload_mb
    enable_llm_explanations: bool = False
    sentry_dsn: str = ""
    # Proxies in front of the app that append to X-Forwarded-For (see app/core/ratelimit.py).
    trusted_proxy_hops: int = 0
    # Header holding the client address set by the edge proxy (Render: true-client-ip). Preferred over
    # TRUSTED_PROXY_HOPS when present and a valid IP (app/core/ratelimit.py).
    client_ip_header: str = ""

    @field_validator("env")
    @classmethod
    def _normalise_env(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        return [o.strip() for o in v.split(",") if o.strip()] if isinstance(v, str) else v

    @model_validator(mode="after")
    def _check(self) -> "Settings":
        dev = self.is_dev
        if not self.jwt_secret and dev:
            self.jwt_secret = secrets.token_urlsafe(48)  # ephemeral: dev tokens stop working on restart
        if len(self.jwt_secret) < MIN_SECRET_LEN or self.jwt_secret.lower() in PLACEHOLDER_SECRETS:
            raise ValueError(
                "JWT_SECRET is missing, a placeholder, or shorter than 32 characters. "
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if not self.cors_origins:
            if not dev:
                raise ValueError("CORS_ORIGINS must list the frontend origin(s), comma-separated.")
            self.cors_origins = ["http://localhost:3000", "http://localhost:5173"]
        if not self.database_url:
            if not dev:
                raise ValueError("DATABASE_URL is required outside ENV=dev (no silent SQLite fallback).")
            self.database_url = "sqlite:///./gaitscan.db"
        if self.database_url.startswith("postgres://"):
            self.database_url = "postgresql://" + self.database_url[len("postgres://") :]
        self.max_upload_bytes = self.max_upload_mb * 1024 * 1024
        return self

    @property
    def is_dev(self) -> bool:
        return self.env in DEV_ENVS

    @property
    def docs_enabled(self) -> bool:
        return self.is_dev


def load_settings(environ: "os._Environ[str] | dict[str, str] | None" = None) -> Settings:
    """Read settings from `environ` (default: the process environment). Keys are case-insensitive."""
    environ = os.environ if environ is None else environ
    try:
        return Settings.model_validate({k.lower(): v for k, v in environ.items()})
    except ValidationError as e:
        # `from None`: the chained ValidationError would print the rejected input value.
        raise RuntimeError(
            "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())
        ) from None


settings = load_settings()
