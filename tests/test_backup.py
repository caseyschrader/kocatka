import sqlite3
from datetime import datetime, timedelta, timezone

from scripts.backup_db import backup


def make_db(path):
    db = sqlite3.connect(path)
    db.execute("create table profiles (id integer)")
    db.execute("insert into profiles values (1), (2)")
    db.commit()
    db.close()


def test_backup_copies_the_data(tmp_path):
    make_db(tmp_path / "kocatka.db")

    target = backup(tmp_path / "kocatka.db", tmp_path / "backups",
                    now=datetime(2026, 11, 22, tzinfo=timezone.utc))

    assert target.name == "kocatka-2026-11-22.db"
    copy = sqlite3.connect(target)
    assert copy.execute("select count(*) from profiles").fetchone()[0] == 2
    copy.close()


def test_backup_keeps_only_the_newest(tmp_path):
    make_db(tmp_path / "kocatka.db")
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)

    for n in range(5):
        backup(tmp_path / "kocatka.db", tmp_path / "backups", keep=3,
               now=start + timedelta(days=n))

    names = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert names == ["kocatka-2026-11-03.db", "kocatka-2026-11-04.db", "kocatka-2026-11-05.db"]


def test_same_day_backup_overwrites(tmp_path):
    make_db(tmp_path / "kocatka.db")
    day = datetime(2026, 11, 22, tzinfo=timezone.utc)

    backup(tmp_path / "kocatka.db", tmp_path / "backups", now=day)
    backup(tmp_path / "kocatka.db", tmp_path / "backups", now=day)

    assert len(list((tmp_path / "backups").iterdir())) == 1
