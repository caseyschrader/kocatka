import pytest
from pydantic import ValidationError

from bot import strings
from bot.config import Settings


def test_no_em_dashes_in_strings():
    for name, value in vars(strings).items():
        if isinstance(value, str) and not name.startswith("_"):
            assert "—" not in value, f"em dash in strings.{name}"


def test_settings_parse_admin_ids():
    settings = Settings(_env_file=None, bot_token="x", admin_ids="1, 22,333")

    assert settings.admin_id_list == [1, 22, 333]


def test_settings_default_database_is_local_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    settings = Settings(_env_file=None, bot_token="x")

    assert settings.database_url.startswith("sqlite+aiosqlite:///")


def test_settings_require_bot_token(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
