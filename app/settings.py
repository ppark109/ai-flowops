from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI FlowOps"
    app_version: str = "0.1.0"
    database_path: str = "data/runtime/app.sqlite3"
    enable_api_agents: bool = False

    @property
    def database_file(self) -> Path:
        return Path(self.database_path)


def _absolute_path(path: str) -> str:
    if path.startswith("."):
        return str(Path(path).resolve())
    return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
