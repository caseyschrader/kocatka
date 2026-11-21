# Kocatka: women-first dating bot for St Petersburg (Telegram MVP)

Kocatka (Косатка) is a Telegram bot to test whether women-first messaging has traction. See `CLAUDE.md` for the full brief and milestones.

Status: milestone 5 (chat relay, report and block, admin ban, /delete_me).

## Commands

| Command | What it does |
| --- | --- |
| `/start` | Starts onboarding, or shows your profile if you already have one |
| `/cancel` | Abandons onboarding. Nothing is saved |
| `/profile` | Shows your profile as others will see it |
| `/browse` | Shows profiles one at a time with Like and Pass buttons |
| `/matches` | Lists your pending and active matches, with a Write or Open chat button |
| `/stop` | Leaves the chat you are in |
| `/delete_me` | Deletes your account and all your data, after a confirmation |
| `/ban <id> [reason]` | Admins only. Bans a user and ends their conversations |
| `/unban <id>` | Admins only |

## Chat

A Write, Reply or Open chat button puts you in a chat with that person. Everything you type goes to them through the bot until you send `/stop`. Text only for now. Only the fact that a message was sent (who, when, length) is stored, never the text.

## Safety

* Every profile card, match message and relayed message has Report and Block buttons.
* Block (after a confirmation) hides both people from each other and ends their match or conversation.
* Report asks for a reason, also blocks, and sends the report with the profile and a Ban button to every admin in `ADMIN_IDS`.
* Banned users are stopped at every message, hidden from browsing, and their conversations end. They can still run `/delete_me`. The ban itself (only the Telegram id) is kept, so they cannot sign up again.

## Admins

Set `ADMIN_IDS` in `.env` to numeric Telegram user ids, comma-separated. Not usernames: message `@userinfobot` in Telegram to see your id. The bot refuses to start if the value is not numeric.

## Matches and the women-first rule

* A like in both directions creates a match with a 24 hour window.
* Woman and man: only the woman can send the first message. The man is told she has 24 hours.
* Same gender: either person can start. Whoever sends first wins, the other is told the conversation has started.
* If nobody writes in time, the match expires and both are told. A background check runs every minute inside the bot, and once at startup.
* After the first message, both people chat freely through the bot.

## How browsing picks a profile

A candidate is shown only if both people fit each other's filters: same city, each wants the other's gender, and each one's age is inside the other's chosen range. Anyone you already liked or passed is never shown again. People who already liked you come first, everyone else in random order.

## Testing with one Telegram account

Browsing needs at least two profiles. You can get a second one by asking a friend, or with a second Telegram account (Telegram allows several accounts in one app).

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
| `bot/jobs.py` | Background work: match expiry, startup catch-up |
| `bot/middlewares.py` | Ban check before every handler |
| `bot/handlers/` | Telegram handlers, one file per feature |
| `bot/services/` | Business rules and queries, no Telegram code |
| `bot/db/` | Tables and database session setup |
| `tests/` | pytest tests. `conftest.py` has a fake Telegram connection |
