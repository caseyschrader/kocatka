r"""Runs every query in analytics/queries and prints the results.

Run: .venv\Scripts\python -m analytics.report [path to database]

Read-only, safe while the bot is running. The queries are written in SQLite's
dialect (date(), json_extract) and get ported when the bot moves to PostgreSQL.
"""

import sqlite3
import sys
from pathlib import Path

QUERIES_DIR = Path(__file__).parent / "queries"


def query_files() -> list[Path]:
    return sorted(QUERIES_DIR.glob("*.sql"))


def title(sql_file: Path) -> str:
    """The first comment line of the file."""
    first = sql_file.read_text(encoding="utf-8").splitlines()[0]
    return first.removeprefix("--").strip()


def run_query(db_path: Path, sql_file: Path) -> tuple[list[str], list[tuple]]:
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cursor = db.execute(sql_file.read_text(encoding="utf-8"))
        columns = [c[0] for c in cursor.description]
        return columns, cursor.fetchall()
    finally:
        db.close()


def format_table(columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return "  (no data yet)"
    cells = [[("" if v is None else str(v)) for v in row] for row in rows]
    widths = [max(len(col), *(len(r[i]) for r in cells)) for i, col in enumerate(columns)]
    line = lambda values: "  " + "  ".join(v.ljust(w) for v, w in zip(values, widths))
    return "\n".join([line(columns), line(["-" * w for w in widths]), *map(line, cells)])


def main() -> None:
    db_path = Path(sys.argv[1] if len(sys.argv) > 1 else "kocatka.db")
    if not db_path.exists():
        print(f"No database at {db_path}. Has the bot been started yet?")
        return
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    has_events = db.execute(
        "select 1 from sqlite_master where type = 'table' and name = 'events'"
    ).fetchone()
    db.close()
    if not has_events:
        print("No events table yet. Restart the bot once with the newest code to create it.")
        return
    for sql_file in query_files():
        columns, rows = run_query(db_path, sql_file)
        print(f"\n{title(sql_file)}\n{format_table(columns, rows)}")


if __name__ == "__main__":
    main()
