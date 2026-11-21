# Russian Bumble: Telegram Bot MVP (Project Brief)

## Goal

Validate, as cheaply as possible, whether a women-first-messaging dating service has traction in St Petersburg. Build a Telegram bot, not a mobile app. Success after the pilot (about 200-500 users): do users come back, do matches turn into conversations, would anyone pay.

## About the builder

Data engineer (Python, SQL, Airflow, cloud). No mobile or app development experience. Explain choices briefly, prefer boring and simple tools, and keep each step small enough to run and test before moving on.

## Constraints

* Python 3.12, aiogram 3 (async Telegram bot framework).
* SQLite for the first milestones, then PostgreSQL via SQLAlchemy and Alembic.
* Run locally with polling first. Docker and a small VPS later.
* All user-facing text in Russian, kept in one strings file so it is easy to edit.
* No em dashes in any text I write or you write for me.

## MVP scope

1. Onboarding: /start, confirm 18+, gender, who they want to meet, age, city (St Petersburg only at first), short bio, 1-3 photos.
2. Browsing: the bot shows one profile at a time with Like / Pass buttons. Filter by gender preference, age range and city. Never show the same profile twice.
3. Matching: a mutual like creates a match.
4. Women-first rule: after a match, only the woman can send the first message. The man sees "she has 24 hours to write first". If she does nothing, the match expires. For same-gender matches, either person may start, but only one may do so within the first 24 hours (a simple tiebreak is fine for the MVP).
5. Chat relay: messages go through the bot so no usernames or phone numbers are exposed. Support text first, photos later.
6. Safety basics: Report and Block on every profile and conversation, an admin command to ban a user, delete-my-account command that removes all stored data.

## Out of scope for now

Payments, native apps, face matching or photo-similarity search, uploading photos of other people, any country other than Russia, and automatic selfie verification (do manual review of the first users instead).

## Data and privacy rules

* Collect the minimum: Telegram user id, first name, age, gender, preference, city, bio, photo file ids.
* No biometric processing of any kind in the MVP.
* Explain what is stored and get explicit consent during onboarding. Provide /delete_me.
* Russian data-storage law and payment/sanctions questions need a local lawyer before any public launch or charging money. Flag anything in the design that touches these.

## Analytics (the data engineering part)

Log every meaningful action as an append-only `events` table: event_id, user_id, event_type, timestamp, properties (JSON). Event types include: signup_started, signup_completed, profile_viewed, like, pass, match_created, first_message_sent, match_expired, report, block, account_deleted. Later milestones: daily export to Parquet, a dbt or SQL model for retention, match rate, and first-message rate, and a simple dashboard.

## Suggested data model

users, profiles, photos, swipes (viewer, target, action, ts), matches (user_a, user_b, status, created_at, expires_at, first_sender), messages, reports, blocks, events.

## Milestones

1. Repo setup, bot responds to /start, config via .env, README with run steps.
2. Onboarding flow and profile storage, with tests.
3. Browsing and like/pass with candidate selection.
4. Matching and the women-first window, including expiry job.
5. Chat relay, report/block, admin ban, /delete_me.
6. Events table and first analytics queries.
7. Dockerize, deploy to a small VPS, invite a first batch of about 20 friendly testers.
8. Optional: a simulation notebook using synthetic users to compare women-first versus open messaging on match-to-conversation rate.

## Working agreement for Claude Code

* Start by proposing the repo structure and wait for my OK.
* After each milestone: run the tests, summarize what changed in a few lines, and tell me how to try it in Telegram.
* Ask before adding any new dependency or service.
* Do not store secrets in the repo.

## Project conventions

* The app is called Kocatka. In Russian user-facing text it is written "Косатка" (`APP_NAME` in `bot/strings.py`).

* Python 3.12 in a local `.venv`. Run the bot with `python -m bot`, run tests with `pytest`.
* All user-facing text lives in `bot/strings.py`.
* Handlers live in `bot/handlers/`, one router per feature. Register new routers in `bot/handlers/__init__.py`, before the fallback router.
* Rules and database queries live in `bot/services/` and import nothing from aiogram.
* Handlers receive a database session as the `session` argument (see `DbSessionMiddleware`).
* Tests drive the real dispatcher through `FakeChat` in `tests/conftest.py`: `send_text`, `send_photo`, `press`. All users in a test share one fake bot; each `FakeChat` sees only calls to its own chat.
* SQLite returns datetimes without a timezone. Wrap loaded values in `as_utc()` before comparing in Python, and pass `synchronize_session=False` on bulk updates that filter on datetimes.
* Time-dependent services take an optional `now` argument so tests can move the clock.
* Handlers get `admin_ids` (list of ints) as an argument, passed to `start_polling` and to `feed_raw_update` in tests. The `admin` fixture makes a test user an admin.
* Relayed message text is never stored, only metadata in `messages`. `delete_user_data` must remove every table that mentions the user, except `bans`.
* On Windows, git is at `C:\Program Files\Git\cmd` and may be missing from PATH in tool shells.
