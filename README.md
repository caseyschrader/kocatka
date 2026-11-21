# Kocatka: women-first dating bot for St Petersburg (Telegram MVP)

Kocatka (Косатка) is a Telegram bot to test whether women-first messaging has traction. See `CLAUDE.md` for the full brief and milestones.

Status: milestone 2 (onboarding and profile storage).

## Commands

| Command | What it does |
| --- | --- |
| `/start` | Starts onboarding, or shows your profile if you already have one |
| `/cancel` | Abandons onboarding. Nothing is saved |
| `/profile` | Shows your profile as others will see it |

## Setup (Windows, PowerShell)

1. Create the virtual environment with Python 3.12 and install dependencies:

   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\python -m pip install -r requirements-dev.txt
   ```

2. Get a bot token: open Telegram, message `@BotFather`, send `/newbot` and follow the prompts.

3. Create your config file and paste the token into it:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

   `.env` is in `.gitignore`. Never commit it.

## Run

```powershell
.venv\Scripts\python -m bot
```

Then open your bot in Telegram and send `/start`. Stop the bot with Ctrl+C.

## Data

Profiles are stored in a local SQLite file, `kocatka.db`, created on first run. It is in `.gitignore`.

* To start over as a new user, stop the bot and delete `kocatka.db`.
* Tables are created automatically but never altered. Until Alembic arrives with PostgreSQL, a milestone that changes the tables means deleting `kocatka.db`.
* Answers given during onboarding live in memory until the last step, so restarting the bot mid-onboarding loses them. The user sends `/start` again.

## Test

```powershell
.venv\Scripts\python -m pytest
```

## Layout

| Path | Purpose |
| --- | --- |
| `bot/__main__.py` | Entry point, starts polling |
| `bot/app.py` | Builds the dispatcher (shared with tests) |
| `bot/config.py` | Settings from `.env` |
| `bot/strings.py` | All Russian user-facing text |
| `bot/keyboards.py` | Inline button layouts |
| `bot/handlers/` | Telegram handlers, one file per feature |
| `bot/services/` | Business rules and queries, no Telegram code |
| `bot/db/` | Tables and database session setup |
| `tests/` | pytest tests. `conftest.py` has a fake Telegram connection |
