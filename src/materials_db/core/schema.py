"""Schema introspection and VIEW setup for the SQL agent."""

import sqlite3

# Adapted to the actual DB schema (optical_nk instead of optical_constants;
# formula as composition; density_g_cm3 as density).
_FLAT_VIEW = """
CREATE VIEW IF NOT EXISTS materials_flat AS
SELECT m.id,
       m.name,
       m.formula      AS composition,
       o.wavelength_nm,
       o.n,
       o.k,
       m.density_g_cm3 AS density,
       NULL            AS bandgap_ev
FROM   materials m
LEFT JOIN optical_nk o ON m.id = o.material_id
"""


def get_schema_summary(conn: sqlite3.Connection) -> str:
    """
    Physical purpose: Introspect all tables and views in the database, create the materials_flat convenience view if absent, and return a compact schema string for injection into LLM prompts.
    Args/Returns: conn — sqlite3 connection (writable for VIEW creation); returns a newline-separated string of ≤400 characters describing each object with column names, FK annotations, and row counts.
    """
    # Create the flat view once; ignore errors if it already exists or a
    # referenced table is missing.
    try:
        conn.execute(_FLAT_VIEW)
        conn.commit()
    except Exception:
        pass

    objects = conn.execute(
        "SELECT name, type FROM sqlite_master "
        "WHERE type IN ('table','view') ORDER BY type, name"
    ).fetchall()

    parts: list[str] = []
    for name, kind in objects:
        try:
            col_rows = conn.execute(f"PRAGMA table_info([{name}])").fetchall()
            cols = [r[1] for r in col_rows]

            # Annotate FK columns with the target table name.
            fk_rows = conn.execute(f"PRAGMA foreign_key_list([{name}])").fetchall()
            fk_map = {r[3]: r[2] for r in fk_rows}  # from_col -> to_table
            col_str = ",".join(
                f"{c}->{fk_map[c]}" if c in fk_map else c for c in cols
            )

            if kind == "table":
                count = conn.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
                parts.append(f"{name}({col_str})[{count}]")
            else:
                parts.append(f"{name}(VIEW:{col_str})")
        except Exception:
            parts.append(name)

    summary = "\n".join(parts)
    if len(summary) > 400:
        summary = summary[:397] + "..."
    return summary
