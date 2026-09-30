"""Read-only SQL guard shared by materials_db.access (release queries) and materials_db.core.sql_agent (MatChat).

Three layers, each sufficient on its own for writes: the database is opened with SQLite `mode=ro`; `PRAGMA query_only` is on; and
ad-hoc SQL runs under a SQLite authorizer that allows reading only (SELECT, column reads, function calls, and four introspection
PRAGMAs). Extension loading stays disabled (Python's default; nothing here enables it). `execute_read_only` also caps the rows
returned and the time a statement may run.
"""
import sqlite3
import time

READ_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}


def authorizer(action, arg1, arg2, dbname, source):
    if action in READ_ACTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_PRAGMA and arg1 in ("table_info", "table_list", "index_list", "foreign_key_list") and arg2 is None:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


class QueryTimeout(sqlite3.OperationalError):
    """The statement ran longer than its time limit and was interrupted."""


def execute_read_only(con, sql, *, max_rows, timeout_s):
    """Run one statement under the authorizer, the row cap and the time cap. Returns (columns, rows, truncated), rows as tuples.
    Raises sqlite3.Error for anything refused (a write, ATTACH, PRAGMA, several statements, ...) and QueryTimeout on the cap."""
    deadline = time.monotonic() + timeout_s
    timed_out = []

    def _progress():
        if time.monotonic() > deadline:
            timed_out.append(True)
            return 1  # non-zero interrupts the statement
        return 0

    con.set_authorizer(authorizer)
    con.set_progress_handler(_progress, 1000)
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in (cur.description or [])]
        rows = cur.fetchmany(max_rows + 1)
    except sqlite3.OperationalError as exc:
        if timed_out:
            raise QueryTimeout(f"query exceeded the {timeout_s:g} s limit") from exc
        raise
    finally:
        con.set_progress_handler(None, 0)
        con.set_authorizer(None)
    return cols, rows[:max_rows], len(rows) > max_rows
