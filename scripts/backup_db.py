"""Copies the database to a dated backup file and keeps only the newest ones.

On the server it runs inside the container, every night from cron:
    docker compose exec -T bot python scripts/backup_db.py /data/kocatka.db /data/backups

Uses SQLite's own backup, which gives a consistent copy even while the bot writes.
"""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

KEEP = 14


def backup(db_path: Path, backup_dir: Path, keep: int = KEEP, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"kocatka-{now:%Y-%m-%d}.db"

    source = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    # Names sort by date, so everything before the newest `keep` files goes.
    for old in sorted(backup_dir.glob("kocatka-*.db"))[:-keep]:
        old.unlink()
    return target


def main() -> None:
    db_path = Path(sys.argv[1] if len(sys.argv) > 1 else "kocatka.db")
    backup_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "backups")
    print(f"Backed up to {backup(db_path, backup_dir)}")


if __name__ == "__main__":
    main()
