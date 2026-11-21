"""Quick counts from the local database. Run: .venv\\Scripts\\python scripts\\stats.py

Read-only. Prints counts only, no names or personal details.
Milestone 6 replaces this with the events table and proper analytics queries.
"""

import sqlite3
import sys
from pathlib import Path

DB = Path(sys.argv[1] if len(sys.argv) > 1 else "kocatka.db")


def main() -> None:
    if not DB.exists():
        print(f"No database at {DB}. Has the bot been started yet?")
        return
    # Open read-only so this can never change data, even while the bot runs.
    db = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    def one(sql: str) -> int:
        return db.execute(sql).fetchone()[0]

    tables = {row[0] for row in db.execute("select name from sqlite_master where type='table'")}

    print(f"Profiles: {one('select count(*) from profiles')}")
    for gender, count in db.execute(
        "select gender, count(*) from profiles group by gender order by gender"
    ):
        print(f"  {gender}: {count}")
    recent = one("select count(*) from profiles where created_at >= datetime('now', '-1 day')")
    print(f"  signed up in the last 24 hours: {recent}")

    print(f"Likes and passes: {one('select count(*) from swipes')}")
    for action, count in db.execute("select action, count(*) from swipes group by action"):
        print(f"  {action}: {count}")

    if "matches" in tables:
        print(f"Matches: {one('select count(*) from matches')}")
        for status, count in db.execute(
            "select status, count(*) from matches group by status order by status"
        ):
            print(f"  {status}: {count}")
    if "messages" in tables:
        print(f"Chat messages sent: {one('select count(*) from messages')}")
    if "bans" in tables:
        print(f"Banned: {one('select count(*) from bans')}")


if __name__ == "__main__":
    main()
