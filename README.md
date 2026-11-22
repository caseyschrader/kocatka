# Kocatka: women-first dating bot for St Petersburg (Telegram MVP)

Kocatka (Косатка) is a Telegram bot to test whether women-first messaging has traction. See `CLAUDE.md` for the full brief and milestones.

Status: milestone 7 (Docker and server deploy). See `docs/DEPLOY.md` for running it on a server and `docs/tester_invite.md` for the tester invite.

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

## Mini App

The bot also runs a small web server for the Telegram Mini App (`webapp/`), on http://127.0.0.1:8080.
Telegram only opens Mini Apps over HTTPS, so inside Telegram it works on the server (see `docs/DEPLOY.md`, step 7).

To look at the page on the laptop in an ordinary browser, add your own Telegram user id to `.env`:

```
DEV_USER_ID=123456789
```

Run the bot and open http://127.0.0.1:8080. The page acts as that user without Telegram's login check.
This only works while the web server listens on 127.0.0.1, and must never be set on the server.

## Data

Profiles are stored in a local SQLite file, `kocatka.db`, created on first run. It is in `.gitignore`.

* To start over as a new user, stop the bot and delete `kocatka.db`.
* Tables are created automatically but never altered. Until Alembic arrives with PostgreSQL, a milestone that changes the tables means deleting `kocatka.db`.
* Answers given during onboarding live in memory until the last step, so restarting the bot mid-onboarding loses them. The user sends `/start` again.

## Analytics

Every meaningful action is logged to an append-only `events` table (`event_id`, `event_type`, `user_id`, `target_id`, `ts`, `properties` as JSON). Event types are listed in `bot/services/events.py`.

To see the funnel, retention, match rate, first-message rate, conversations and safety numbers:

```powershell
.venv\Scripts\python -m analytics.report
```

The queries are plain SQL files in `analytics/queries/`, one question each, in SQLite's dialect for now. Read-only, safe while the bot is running.

Privacy rules for events:

* `signup_started` and `signup_stopped` happen before consent and carry no user id.
* Properties never hold names, text or other personal details, only things like `match_id`, `reason` or message length.
* On `/delete_me` the user's id in every event is replaced with a random negative number. The history still counts toward totals and retention, but no longer points to the person.

## Quick stats

```powershell
.venv\Scripts\python scripts\stats.py
```

Prints counts of profiles, likes, matches, messages and bans. Read-only, safe to run while the bot is running.

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
| `webapp/server.py` | Mini App web server: login check and JSON API |
| `webapp/auth.py` | Checks Telegram's signature on Mini App requests |
| `webapp/photos.py` | Signed, hour-long photo links; fetches photos from Telegram without storing them |
| `webapp/static/` | The Mini App page: HTML, JavaScript, CSS |
| `Caddyfile` | HTTPS in front of the Mini App on the server |
| `tests/` | pytest tests. `conftest.py` has a fake Telegram connection |
