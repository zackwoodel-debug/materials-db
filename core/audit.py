"""DB integrity check run at agent startup."""

import sqlite3
from pathlib import Path

from rich.console import Console
from rich.table import Table

_ROOT = Path(__file__).resolve().parent.parent
_DB = _ROOT / "data" / "materials.db"
_con = Console()


def run_audit() -> bool:
    """
    Physical purpose: Verify that data/materials.db exists and is populated before the agent starts, printing a Rich table of table names and row counts.
    Args/Returns: no arguments; returns True if the DB is present and contains at least one row, False otherwise.
    """
    if not _DB.exists():
        _con.print(f"[bold red]✗ DB not found:[/bold red] {_DB}\n  Run init_db.py first.")
        return False

    try:
        conn = sqlite3.connect(str(_DB))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

        if not tables:
            _con.print("[bold red]✗ Database has no tables.[/bold red]")
            conn.close()
            return False

        tbl = Table(title="DB Audit", header_style="bold blue", show_lines=False)
        tbl.add_column("Table", style="cyan")
        tbl.add_column("Rows", justify="right", style="green")

        total = 0
        for (name,) in tables:
            count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
            tbl.add_row(name, f"{count:,}")
            total += count

        conn.close()
        _con.print(tbl)

        if total == 0:
            _con.print("[bold red]✗ All tables are empty.[/bold red]")
            return False

        _con.print(
            f"[bold green]✓ Audit passed.[/bold green] "
            f"{len(tables)} tables · {total:,} total rows."
        )
        return True

    except Exception as exc:
        _con.print(f"[bold red]✗ Audit error:[/bold red] {exc}")
        return False


if __name__ == "__main__":
    run_audit()
