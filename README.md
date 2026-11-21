# Kocatka: women-first dating bot for St Petersburg (Telegram MVP)

Kocatka (Косатка) is a Telegram bot to test whether women-first messaging has traction. See `CLAUDE.md` for the full brief and milestones.

Status: milestone 1 (the bot answers `/start`).

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

## Test

```powershell
.venv\Scripts\python -m pytest
```

## Layout

| Path | Purpose |
| --- | --- |
| `bot/__main__.py` | Entry point, starts polling |
| `bot/config.py` | Settings from `.env` |
| `bot/strings.py` | All Russian user-facing text |
| `bot/handlers/` | One file per feature |
| `tests/` | pytest tests |
