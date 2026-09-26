"""Runtime configuration, read once from environment variables.

Fails closed: ENV defaults to "production", and production refuses to start
with a missing/placeholder JWT secret or without an explicit CORS allow-list.
"""
import os
import secrets
from dataclasses import dataclass

DEV_ENVS = {"dev", "development", "test"}
MIN_SECRET_LEN = 32
PLACEHOLDER_SECRETS = {"change-me", "changeme", "your_jwt_secret_here", "secret"}
DEV_ORIGINS = ["http://localhost:3000"]


@dataclass
class Settings:
    env: str
    jwt_secret: str
    cors_origins: list
    access_token_minutes: int
    max_upload_bytes: int
    enable_llm: bool

    @property
    def is_dev(self) -> bool:
        return self.env in DEV_ENVS

    @property
    def docs_enabled(self) -> bool:
        return self.is_dev


def load_settings(environ=os.environ) -> Settings:
    env = environ.get("ENV", "production").strip().lower()
    dev = env in DEV_ENVS

    secret = environ.get("JWT_SECRET", "")
    if not secret and dev:
        secret = secrets.token_urlsafe(48)  # ephemeral: dev tokens stop working on restart
    if len(secret) < MIN_SECRET_LEN or secret.lower() in PLACEHOLDER_SECRETS:
        raise RuntimeError(
            "JWT_SECRET is missing, a placeholder, or shorter than 32 characters. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )

    origins = [o.strip() for o in environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    if not origins:
        if not dev:
            raise RuntimeError("CORS_ORIGINS must list the frontend origin(s), comma-separated.")
        origins = DEV_ORIGINS

    return Settings(
        env=env,
        jwt_secret=secret,
        cors_origins=origins,
        access_token_minutes=int(environ.get("ACCESS_TOKEN_MINUTES", 12 * 60)),
        max_upload_bytes=int(environ.get("MAX_UPLOAD_MB", 100)) * 1024 * 1024,
        enable_llm=environ.get("ENABLE_LLM_EXPLANATIONS", "").lower() in ("1", "true", "yes"),
    )


settings = load_settings()
