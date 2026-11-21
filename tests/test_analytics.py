"""The analytics queries, checked against seeded events with known answers."""

from datetime import datetime, timedelta, timezone

import pytest

from analytics.report import format_table, query_files, run_query, title
from bot.services.events import log_event

DAY0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
QUERIES = {f.stem: f for f in query_files()}


def day(n: int, hours: int = 0) -> datetime:
    return DAY0 + timedelta(days=n, hours=hours)


@pytest.fixture
def db_path(tmp_path, sessionmaker):
    # The same file the sessionmaker fixture writes to.
    return tmp_path / "test.db"


async def seed(sessionmaker, rows) -> None:
    async with sessionmaker() as session:
        for event_type, user_id, target_id, ts, props in rows:
            log_event(session, event_type, user_id, target_id, ts, **props)
        await session.commit()


def as_dicts(db_path, name):
    columns, rows = run_query(db_path, QUERIES[name])
    return [dict(zip(columns, row)) for row in rows]


async def test_signup_funnel_and_reasons(sessionmaker, db_path):
    await seed(sessionmaker, [
        ("signup_started", None, None, day(0), {}),
        ("signup_started", None, None, day(0), {}),
        ("signup_started", None, None, day(0), {}),
        ("signup_stopped", None, None, day(0), {"reason": "underage"}),
        ("signup_completed", 1, None, day(0), {}),
        ("signup_completed", 2, None, day(0), {}),
    ])

    assert as_dicts(db_path, "01_signup_funnel") == [
        {"day": "2026-11-01", "started": 3, "stopped": 1, "completed": 2, "completed_pct": 66.7}
    ]
    assert as_dicts(db_path, "02_signup_stop_reasons") == [{"reason": "underage", "times": 1}]


async def test_daily_active_ignores_system_events(sessionmaker, db_path):
    await seed(sessionmaker, [
        ("like", 1, 2, day(0), {}),
        ("like", 1, 3, day(0), {}),
        ("pass", 2, 1, day(0), {}),
        ("match_expired", 3, 4, day(0), {"match_id": 1}),
        ("profile_viewed", 1, 2, day(1), {}),
    ])

    assert as_dicts(db_path, "03_daily_active_users") == [
        {"day": "2026-11-01", "active_users": 2},
        {"day": "2026-11-02", "active_users": 1},
    ]


async def test_retention(sessionmaker, db_path):
    await seed(sessionmaker, [
        ("signup_completed", 1, None, day(0), {}),
        ("like", 1, 9, day(1), {}),  # back on day 1
        ("signup_completed", 2, None, day(0), {}),
        ("message_sent", 2, 9, day(7), {"match_id": 1, "length": 3}),  # back on day 7
        ("signup_completed", 3, None, day(0), {}),
        ("like", 3, 9, day(0, hours=2), {}),  # same day only: does not count as coming back
        ("signup_completed", 4, None, day(1), {}),
    ])

    assert as_dicts(db_path, "04_retention") == [
        {"cohort": "2026-11-01", "signups": 3, "day1": 1, "day7": 1,
         "came_back_ever": 2, "came_back_pct": 66.7},
        {"cohort": "2026-11-02", "signups": 1, "day1": 0, "day7": 0,
         "came_back_ever": 0, "came_back_pct": 0.0},
    ]


async def test_match_rate(sessionmaker, db_path):
    await seed(sessionmaker, [
        ("profile_viewed", 1, 2, day(0), {}),
        ("like", 1, 2, day(0), {}),
        ("profile_viewed", 2, 1, day(0), {}),
        ("like", 2, 1, day(0), {}),
        ("match_created", 1, 2, day(0), {"match_id": 1, "same_gender": False}),
        ("profile_viewed", 1, 3, day(0), {}),
        ("pass", 1, 3, day(0), {}),
    ])

    assert as_dicts(db_path, "05_match_rate") == [
        {"day": "2026-11-01", "views": 3, "likes": 2, "passes": 1, "matches": 1,
         "matches_per_100_likes": 50.0}
    ]


async def test_first_message_rate(sessionmaker, db_path):
    mixed = {"same_gender": False}
    await seed(sessionmaker, [
        ("match_created", 1, 2, day(0), {"match_id": 1, **mixed}),
        ("first_message_sent", 1, 2, day(0, 2), {"match_id": 1, "seconds_since_match": 7200}),
        ("match_created", 3, 4, day(0), {"match_id": 2, **mixed}),
        ("match_expired", 3, 4, day(1), {"match_id": 2}),
        ("match_created", 5, 6, day(0), {"match_id": 3, "same_gender": True}),
        ("first_message_sent", 5, 6, day(0, 1), {"match_id": 3, "seconds_since_match": 3600}),
        ("match_created", 7, 8, day(0), {"match_id": 4, **mixed}),  # still pending
        ("match_created", 9, 10, day(0), {"match_id": 5, **mixed}),
        ("match_closed", 9, 10, day(0, 3), {"match_id": 5, "reason": "block"}),
    ])

    assert as_dicts(db_path, "06_first_message_rate") == [
        {"pair": "same gender", "matches": 1, "first_message": 1, "expired": 0,
         "closed_before_message": 0, "still_pending": 0, "first_message_pct": 100.0,
         "avg_hours_to_first": 1.0},
        {"pair": "woman and man", "matches": 4, "first_message": 1, "expired": 1,
         "closed_before_message": 1, "still_pending": 1, "first_message_pct": 50.0,
         "avg_hours_to_first": 2.0},
    ]


async def test_conversations(sessionmaker, db_path):
    await seed(sessionmaker, [
        ("first_message_sent", 1, 2, day(0), {"match_id": 1, "seconds_since_match": 60}),
        ("message_sent", 1, 2, day(0), {"match_id": 1, "length": 5}),
        ("message_sent", 2, 1, day(0), {"match_id": 1, "length": 5}),
        ("first_message_sent", 5, 6, day(0), {"match_id": 3, "seconds_since_match": 60}),
        ("message_sent", 5, 6, day(0), {"match_id": 3, "length": 5}),
    ])

    assert as_dicts(db_path, "07_conversations") == [
        {"conversations": 2, "got_a_reply": 1, "reply_pct": 50.0,
         "ten_plus_messages": 0, "avg_messages": 1.5}
    ]


async def test_safety(sessionmaker, db_path):
    await seed(sessionmaker, [
        ("report", 1, 2, day(0), {"reason": "rude"}),
        ("block", 1, 2, day(0), {"via_report": True}),
        ("user_banned", 2, None, day(0), {}),
        ("account_deleted", -5, None, day(1), {}),
    ])

    assert as_dicts(db_path, "08_safety") == [
        {"day": "2026-11-01", "reports": 1, "blocks": 1, "bans": 1, "deletions": 0},
        {"day": "2026-11-02", "reports": 0, "blocks": 0, "bans": 0, "deletions": 1},
    ]


async def test_every_query_runs_on_empty_and_real_data(new_chat, sessionmaker, db_path):
    from tests.test_chat import chatting_pair

    for sql_file in query_files():
        assert title(sql_file)
        format_table(*run_query(db_path, sql_file))

    await chatting_pair(new_chat)
    for sql_file in query_files():
        assert format_table(*run_query(db_path, sql_file))
