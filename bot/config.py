"""Settings loaded from environment variables or a local .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_ids: str = ""
    database_url: str = "sqlite+aiosqlite:///kocatka.db"

    @property
    def admin_id_list(self) -> list[int]:
        return [int(part) for part in self.admin_ids.split(",") if part.strip()]


def load_settings() -> Settings:
    """Fails with a clear validation error if BOT_TOKEN is missing."""
    return Settings()
