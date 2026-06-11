#!/usr/bin/env python3
"""Audit the current materials.db without assuming its schema."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "materials.db"
DEFAULT_OUTPUT = ROOT / "schema_audit.md"


def fetchall_dicts(conn: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def list_objects(conn: sqlite3.Connection) -> list[dict]:
    return fetchall_dicts(
        conn,
        """
        SELECT name, type, sql
        FROM sqlite_master
        WHERE type IN ('table', 'view')
        ORDER BY type, name
        """,
    )


def table_info(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    return fetchall_dicts(conn, f"PRAGMA table_info({quote_identifier(table_name)})")


def foreign_keys(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    return fetchall_dicts(conn, f"PRAGMA foreign_key_list({quote_identifier(table_name)})")


def row_count(conn: sqlite3.Connection, table_name: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {quote_identifier(table_name)}").fetchone()[0]


def duplicate_material_names(conn: sqlite3.Connection) -> list[tuple]:
    objects = {obj["name"] for obj in list_objects(conn)}
    if "materials" not in objects:
        return []

    columns = {column["name"].lower(): column["name"] for column in table_info(conn, "materials")}
    if "name" not in columns:
        return []

    name_column = quote_identifier(columns["name"])
    return conn.execute(
        f"""
        SELECT LOWER(TRIM({name_column})) AS normalized_name, COUNT(*) AS count
        FROM materials
        WHERE {name_column} IS NOT NULL AND TRIM({name_column}) != ''
        GROUP BY LOWER(TRIM({name_column}))
        HAVING COUNT(*) > 1
        ORDER BY count DESC, normalized_name
        """
    ).fetchall()


def orphan_records(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    orphans = []
    for fk in foreign_keys(conn, table_name):
        from_col = fk["from"]
        to_table = fk["table"]
        to_col = fk["to"]
        count = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {quote_identifier(table_name)} child
            LEFT JOIN {quote_identifier(to_table)} parent
              ON child.{quote_identifier(from_col)} = parent.{quote_identifier(to_col)}
            WHERE child.{quote_identifier(from_col)} IS NOT NULL
              AND parent.{quote_identifier(to_col)} IS NULL
            """
        ).fetchone()[0]
        if count:
            orphans.append(
                {
                    "table": table_name,
                    "column": from_col,
                    "parent_table": to_table,
                    "parent_column": to_col,
                    "orphan_count": count,
                }
            )
    return orphans


def implied_missing_foreign_keys(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    declared = {(fk["from"], fk["table"]) for fk in foreign_keys(conn, table_name)}
    existing_tables = {obj["name"] for obj in list_objects(conn)}
    columns = table_info(conn, table_name)
    findings = []

    for column in columns:
        column_name = column["name"]
        lower = column_name.lower()
        candidate_parent = None
        candidate_column = None
        if lower == "material_id" and "materials" in existing_tables:
            candidate_parent = "materials"
            candidate_column = "id"
        elif lower in {"reference_id", "source_id"} and "references_db" in existing_tables:
            candidate_parent = "references_db"
            candidate_column = "id"

        if not candidate_parent or (column_name, candidate_parent) in declared:
            continue

        parent_columns = {col["name"] for col in table_info(conn, candidate_parent)}
        if candidate_column not in parent_columns:
            continue

        missing_count = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM {quote_identifier(table_name)} child
            LEFT JOIN {quote_identifier(candidate_parent)} parent
              ON child.{quote_identifier(column_name)} = parent.{quote_identifier(candidate_column)}
            WHERE child.{quote_identifier(column_name)} IS NOT NULL
              AND parent.{quote_identifier(candidate_column)} IS NULL
            """
        ).fetchone()[0]
        findings.append(
            {
                "table": table_name,
                "column": column_name,
                "suggested_parent": candidate_parent,
                "suggested_parent_column": candidate_column,
                "orphan_count_if_enforced": missing_count,
            }
        )
    return findings


def dataset_overlap(conn: sqlite3.Connection) -> list[dict]:
    material_sets = {}
    for obj in list_objects(conn):
        if obj["type"] != "table":
            continue
        columns = {column["name"] for column in table_info(conn, obj["name"])}
        if "material_id" not in columns:
            continue
        rows = conn.execute(
            f"SELECT DISTINCT material_id FROM {quote_identifier(obj['name'])} WHERE material_id IS NOT NULL"
        ).fetchall()
        material_sets[obj["name"]] = {row[0] for row in rows}

    overlaps = []
    names = sorted(material_sets)
    for left_index, left in enumerate(names):
        for right in names[left_index + 1 :]:
            left_set = material_sets[left]
            right_set = material_sets[right]
            shared = left_set & right_set
            if shared:
                overlaps.append(
                    {
                        "dataset_a": left,
                        "dataset_b": right,
                        "shared_materials": len(shared),
                        "a_materials": len(left_set),
                        "b_materials": len(right_set),
                    }
                )
    return overlaps


def write_report(conn: sqlite3.Connection, output_path: Path) -> None:
    objects = list_objects(conn)
    tables = [obj for obj in objects if obj["type"] == "table"]
    views = [obj for obj in objects if obj["type"] == "view"]

    lines = [
        "# Schema Audit",
        "",
        f"Database: `{DEFAULT_DB}`",
        "",
        "## Objects",
        "",
        "| Name | Type | Rows |",
        "| --- | --- | ---: |",
    ]

    for obj in objects:
        rows = row_count(conn, obj["name"]) if obj["type"] == "table" else "view"
        lines.append(f"| `{obj['name']}` | {obj['type']} | {rows} |")

    lines.extend(["", "## Tables", ""])
    for table in tables:
        lines.extend(
            [
                f"### `{table['name']}`",
                "",
                f"Rows: {row_count(conn, table['name'])}",
                "",
                "| Column | Type | Not Null | Default | Primary Key |",
                "| --- | --- | ---: | --- | ---: |",
            ]
        )
        for column in table_info(conn, table["name"]):
            lines.append(
                f"| `{column['name']}` | `{column['type']}` | {column['notnull']} | "
                f"`{column['dflt_value']}` | {column['pk']} |"
            )

        fks = foreign_keys(conn, table["name"])
        lines.extend(["", "Declared foreign keys:"])
        if fks:
            for fk in fks:
                lines.append(
                    f"- `{fk['from']}` -> `{fk['table']}.{fk['to']}` "
                    f"(on delete: `{fk['on_delete']}`)"
                )
        else:
            lines.append("- None declared.")
        lines.append("")

    lines.extend(["## Views", ""])
    if views:
        for view in views:
            lines.extend([f"### `{view['name']}`", "", "```sql", view["sql"] or "", "```", ""])
    else:
        lines.append("No views found.")

    lines.extend(["", "## Duplicate Material Names", ""])
    duplicates = duplicate_material_names(conn)
    if duplicates:
        lines.extend(["| Normalized Name | Count |", "| --- | ---: |"])
        for name, count in duplicates:
            lines.append(f"| `{name}` | {count} |")
    else:
        lines.append("No duplicate material names found after lower-case trim normalization.")

    all_orphans = []
    missing_fks = []
    for table in tables:
        all_orphans.extend(orphan_records(conn, table["name"]))
        missing_fks.extend(implied_missing_foreign_keys(conn, table["name"]))

    lines.extend(["", "## Orphan Records", ""])
    if all_orphans:
        lines.extend(["| Table | Column | Parent | Orphans |", "| --- | --- | --- | ---: |"])
        for item in all_orphans:
            lines.append(
                f"| `{item['table']}` | `{item['column']}` | "
                f"`{item['parent_table']}.{item['parent_column']}` | {item['orphan_count']} |"
            )
    else:
        lines.append("No orphan records found for declared foreign keys.")

    lines.extend(["", "## Missing Foreign Keys", ""])
    if missing_fks:
        lines.extend(
            [
                "| Table | Column | Suggested Parent | Orphans If Enforced |",
                "| --- | --- | --- | ---: |",
            ]
        )
        for item in missing_fks:
            lines.append(
                f"| `{item['table']}` | `{item['column']}` | "
                f"`{item['suggested_parent']}.{item['suggested_parent_column']}` | "
                f"{item['orphan_count_if_enforced']} |"
            )
    else:
        lines.append("No obvious missing material/reference foreign keys detected.")

    lines.extend(["", "## Dataset Overlap", ""])
    overlaps = dataset_overlap(conn)
    if overlaps:
        lines.extend(
            [
                "| Dataset A | Dataset B | Shared Materials | A Materials | B Materials |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for item in overlaps:
            lines.append(
                f"| `{item['dataset_a']}` | `{item['dataset_b']}` | "
                f"{item['shared_materials']} | {item['a_materials']} | {item['b_materials']} |"
            )
    else:
        lines.append("No material_id overlap found across property tables.")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with sqlite3.connect(args.db) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        write_report(conn, args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
