"""Settings read from the environment or a .env file at the repo root."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://ssc:ssc@localhost:5432/ssc"
    data_dir: Path = ROOT / "data"
    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
