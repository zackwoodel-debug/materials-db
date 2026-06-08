"""Keyword-based retriever that grounds API responses in database rows."""

import sqlite3
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_DB = str(_ROOT / "data" / "materials.db")

# The six materials currently seeded in materials.db; extend this list as new
# entries are added so the retriever can match them.
_KNOWN = ["dppc", "peg", "pmma", "polystyrene", "water", "ethanol"]


def retrieve(query: str) -> list[dict]:
    """
    Physical purpose: Match material names in the query to rows in optical_nk and mechanical_qcmd, returning only values that exist in the database.
    Args/Returns: query — natural language string from the user; returns list of row dicts with material_name included, or [] if no known material is mentioned in the query.
    """
    lowered = query.lower()
    matches = [m for m in _KNOWN if m in lowered]
    if not matches:
        return []

    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    rows: list[dict] = []

    for match in matches:
        # Join optical_nk with materials so every returned row carries the
        # material name alongside the optical constants.
        optical = conn.execute(
            """
            SELECT o.id, o.wavelength_nm, o.n, o.k, o.source_ref, o.temperature_C,
                   m.name AS material_name, m.formula, m.material_class
            FROM   optical_nk o
            JOIN   materials  m ON m.id = o.material_id
            WHERE  m.name LIKE ?
            """,
            (f"%{match}%",),
        ).fetchall()
        rows.extend(dict(r) for r in optical)

        # Mechanical data lives in a separate table that only exists in the
        # src/db schema; skip gracefully if the main DB does not have it.
        try:
            mech = conn.execute(
                """
                SELECT q.*, m.name AS material_name
                FROM   mechanical_qcmd q
                JOIN   materials       m ON m.id = q.material_id
                WHERE  m.name LIKE ?
                """,
                (f"%{match}%",),
            ).fetchall()
            rows.extend(dict(r) for r in mech)
        except sqlite3.OperationalError:
            pass

    conn.close()
    return rows
