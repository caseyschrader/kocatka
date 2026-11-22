"""Settings loaded from environment variables or a local .env file."""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_ids: str = ""
    database_url: str = "sqlite+aiosqlite:///kocatka.db"

    # Mini App. WEBAPP_URL is the public https address of the page. When it is
    # empty, the web server still runs locally but Telegram gets no menu button.
    webapp_url: str = ""
    web_host: str = "127.0.0.1"
    web_port: int = 8080
    # Local testing in an ordinary browser: act as this Telegram user without
    # Telegram's signature. Refused unless the server only listens on this computer.
    dev_user_id: int | None = None

    @field_validator("webapp_url")
    @classmethod
    def webapp_url_is_https(cls, value: str) -> str:
        if value and not value.startswith("https://"):
            raise ValueError("WEBAPP_URL must start with https://, Telegram requires it.")
        return value.rstrip("/")

    @model_validator(mode="after")
    def dev_mode_only_on_localhost(self) -> "Settings":
        if self.dev_user_id is not None and self.web_host not in ("127.0.0.1", "localhost"):
            raise ValueError(
                "DEV_USER_ID skips Telegram's login check, so it only works with "
                "WEB_HOST=127.0.0.1. Never set it on the server."
            )
        return self

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
