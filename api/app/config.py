from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """API settings, read from the environment or the repository's root `.env`."""

    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://aicontrol:aicontrol@localhost:5442/aicontrol"

    # Origins of the web UI allowed to call the JSON API from a browser (a JSON list in the env):
    # the Vite dev server (5173) and `vite preview` of the production build (4173).
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ]

    s3_endpoint_url: str | None = "http://localhost:9100"
    s3_bucket: str = "aicontrol-traces"
    s3_access_key: str = "aicontrol"
    s3_secret_key: str = "aicontrol-secret"
    s3_region: str = "us-east-1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
