"""Settings loaded from environment variables or a local .env file."""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_ids: str = ""
    database_url: str = "sqlite+aiosqlite:///kocatka.db"

    @field_validator("admin_ids")
    @classmethod
    def admin_ids_are_numbers(cls, value: str) -> str:
        for part in value.split(","):
            part = part.strip().strip('"').strip("'")
            if part and not part.isdecimal():
                raise ValueError(
                    f"ADMIN_IDS must be numeric Telegram user ids, not usernames: {part!r}. "
                    "Message @userinfobot in Telegram to see your id."
                )
        return value

    @property
    def admin_id_list(self) -> list[int]:
        parts = (p.strip().strip('"').strip("'") for p in self.admin_ids.split(","))
        return [int(p) for p in parts if p]


def load_settings() -> Settings:
    """Fails with a clear validation error if BOT_TOKEN is missing or ADMIN_IDS is wrong."""
    return Settings()
