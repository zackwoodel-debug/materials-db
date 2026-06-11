#!/usr/bin/env python3
"""Populate identity, descriptors, and chemical similarity for normalized DB."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "materials_normalized.db"
IDENTITY_REPORT = ROOT / "identity_population_report.md"
UNRESOLVED_CSV = ROOT / "unresolved_materials.csv"
DESCRIPTOR_FAILURES_CSV = ROOT / "descriptor_failures.csv"
DUPLICATE_REPORT = ROOT / "duplicate_materials_report.md"

IDENTITY_COLUMNS = {
    "formula": "MolecularFormula",
    "smiles": "CanonicalSMILES",
    "inchikey": "InChIKey",
    "molecular_weight": "MolecularWeight",
    "pubchem_cid": "CID",
}


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({quote_identifier(table)})")}


def require_schema(conn: sqlite3.Connection) -> dict[str, set[str]]:
    schema = {
        "materials": columns(conn, "materials"),
        "material_synonyms": columns(conn, "material_synonyms"),
        "chemical_descriptors": columns(conn, "chemical_descriptors"),
    }
    required = {
        "materials": {"material_id", "name"},
        "material_synonyms": {"material_id", "synonym"},
        "chemical_descriptors": {"material_id"},
    }
    missing = {
        table: sorted(required_columns - schema[table])
        for table, required_columns in required.items()
        if required_columns - schema[table]
    }
    if missing:
        raise RuntimeError(f"Missing required schema elements: {missing}")
    return schema


def fetch_pubchem(name: str) -> dict | None:
    properties = ",".join(
        [
            "MolecularFormula",
            "CanonicalSMILES",
            "IsomericSMILES",
            "InChIKey",
            "MolecularWeight",
            "Title",
        ]
    )
    encoded = urllib.parse.quote(name)
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
        f"{encoded}/property/{properties}/JSON"
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError):
        return None

    rows = payload.get("PropertyTable", {}).get("Properties", [])
    if not rows:
        return None
    result = rows[0]
    if "CID" not in result:
        return None
    result["Synonyms"] = fetch_pubchem_synonyms(int(result["CID"]))
    return result


def fetch_pubchem_synonyms(cid: int) -> list[str]:
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError, json.JSONDecodeError):
        return []
    infos = payload.get("InformationList", {}).get("Information", [])
    if not infos:
        return []
    return [synonym for synonym in infos[0].get("Synonym", []) if synonym][:50]


def update_material_identity(
    conn: sqlite3.Connection,
    material: sqlite3.Row,
    pubchem: dict,
    material_columns: set[str],
) -> list[str]:
    updates = {}
    for db_column, pubchem_key in IDENTITY_COLUMNS.items():
        if db_column not in material_columns:
            continue
        if material[db_column] not in (None, ""):
            continue
        value = pubchem.get(pubchem_key)
        if value not in (None, ""):
            updates[db_column] = value

    if "smiles" in material_columns and material["smiles"] in (None, ""):
        smiles = pubchem.get("CanonicalSMILES") or pubchem.get("IsomericSMILES")
        if smiles:
            updates["smiles"] = smiles

    if updates:
        assignments = ", ".join(f"{quote_identifier(column)} = ?" for column in updates)
        values = list(updates.values()) + [material["material_id"]]
        conn.execute(
            f"UPDATE materials SET {assignments} WHERE material_id = ?",
            values,
        )
    return sorted(updates)


def insert_synonyms(conn: sqlite3.Connection, material_id: int, synonyms: list[str]) -> int:
    inserted = 0
    for synonym in synonyms:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO material_synonyms(material_id, synonym)
            VALUES(?, ?)
            """,
            (material_id, synonym[:500]),
        )
        inserted += cursor.rowcount
    return inserted


def import_descriptor_libraries():
    chemical_descriptors_error = None
    try:
        import chemical_descriptors  # noqa: F401
    except Exception as exc:
        chemical_descriptors_error = str(exc)

    from rdkit import Chem, DataStructs
    from rdkit.Chem import Crippen, Descriptors, rdFingerprintGenerator, rdMolDescriptors

    return {
        "Chem": Chem,
        "DataStructs": DataStructs,
        "Crippen": Crippen,
        "Descriptors": Descriptors,
        "rdFingerprintGenerator": rdFingerprintGenerator,
        "rdMolDescriptors": rdMolDescriptors,
        "chemical_descriptors_error": chemical_descriptors_error,
    }


def compute_descriptor(smiles: str, libs: dict) -> tuple[dict | None, str | None]:
    Chem = libs["Chem"]
    Crippen = libs["Crippen"]
    Descriptors = libs["Descriptors"]
    rdFingerprintGenerator = libs["rdFingerprintGenerator"]
    rdMolDescriptors = libs["rdMolDescriptors"]

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None, "invalid SMILES"

    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fingerprint = generator.GetFingerprint(molecule).ToBitString()
    descriptor_json = {
        "source_libraries": ["RDKit", "Chemical-Descriptors"],
        "chemical_descriptors_import": "ok"
        if libs["chemical_descriptors_error"] is None
        else f"failed: {libs['chemical_descriptors_error']}",
        "canonical_smiles": Chem.MolToSmiles(molecule),
    }
    return (
        {
            "exact_mass": float(Descriptors.ExactMolWt(molecule)),
            "tpsa": float(rdMolDescriptors.CalcTPSA(molecule)),
            "logp": float(Crippen.MolLogP(molecule)),
            "heavy_atom_count": int(molecule.GetNumHeavyAtoms()),
            "rotatable_bonds": int(rdMolDescriptors.CalcNumRotatableBonds(molecule)),
            "hbond_donors": int(rdMolDescriptors.CalcNumHBD(molecule)),
            "hbond_acceptors": int(rdMolDescriptors.CalcNumHBA(molecule)),
            "aromatic_rings": int(rdMolDescriptors.CalcNumAromaticRings(molecule)),
            "descriptor_json": json.dumps(descriptor_json, sort_keys=True),
            "morgan_fp": fingerprint,
        },
        None,
    )


def upsert_descriptor(conn: sqlite3.Connection, material_id: int, descriptor: dict, descriptor_columns: set[str]) -> None:
    values = {"material_id": material_id}
    for column, value in descriptor.items():
        if column in descriptor_columns:
            values[column] = value

    insert_columns = list(values)
    placeholders = ", ".join("?" for _column in insert_columns)
    assignments = ", ".join(
        f"{quote_identifier(column)} = excluded.{quote_identifier(column)}"
        for column in insert_columns
        if column != "material_id"
    )
    conn.execute(
        f"""
        INSERT INTO chemical_descriptors({", ".join(quote_identifier(column) for column in insert_columns)})
        VALUES({placeholders})
        ON CONFLICT(material_id) DO UPDATE SET {assignments}
        """,
        [values[column] for column in insert_columns],
    )


def ensure_similarity_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chemical_similarity (
            material_id_1 INTEGER NOT NULL REFERENCES materials(material_id) ON DELETE CASCADE,
            material_id_2 INTEGER NOT NULL REFERENCES materials(material_id) ON DELETE CASCADE,
            tanimoto_similarity REAL NOT NULL,
            PRIMARY KEY(material_id_1, material_id_2),
            CHECK(material_id_1 < material_id_2)
        )
        """
    )


def populate_similarity(conn: sqlite3.Connection, libs: dict) -> int:
    DataStructs = libs["DataStructs"]
    rows = conn.execute(
        """
        SELECT material_id, morgan_fp
        FROM chemical_descriptors
        WHERE morgan_fp IS NOT NULL AND morgan_fp != ''
        ORDER BY material_id
        """
    ).fetchall()
    fingerprints = [
        (row[0], DataStructs.CreateFromBitString(row[1]))
        for row in rows
    ]
    inserted = 0
    for left_index, (left_id, left_fp) in enumerate(fingerprints):
        for right_id, right_fp in fingerprints[left_index + 1 :]:
            similarity = float(DataStructs.TanimotoSimilarity(left_fp, right_fp))
            conn.execute(
                """
                INSERT OR REPLACE INTO chemical_similarity(
                    material_id_1, material_id_2, tanimoto_similarity
                )
                VALUES(?, ?, ?)
                """,
                (left_id, right_id, similarity),
            )
            inserted += 1
    return inserted


def duplicate_groups(conn: sqlite3.Connection, column: str) -> list[tuple[str, list[tuple[int, str]]]]:
    rows = conn.execute(
        f"""
        SELECT material_id, name, {quote_identifier(column)} AS value
        FROM materials
        WHERE {quote_identifier(column)} IS NOT NULL
          AND TRIM(CAST({quote_identifier(column)} AS TEXT)) != ''
        """
    ).fetchall()
    grouped: dict[str, list[tuple[int, str]]] = {}
    for material_id, name, value in rows:
        key = str(value).strip().lower()
        grouped.setdefault(key, []).append((material_id, name))
    return [(key, group) for key, group in sorted(grouped.items()) if len(group) > 1]


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_duplicate_report(conn: sqlite3.Connection, material_columns: set[str]) -> None:
    lines = ["# Duplicate Materials Report", ""]
    checks = [column for column in ["name", "inchikey", "smiles"] if column in material_columns]
    for column in checks:
        lines.extend([f"## Duplicate `{column}`", ""])
        groups = duplicate_groups(conn, column)
        if not groups:
            lines.append("No duplicates detected.")
        else:
            for key, group in groups:
                members = ", ".join(f"{material_id}:{name}" for material_id, name in group)
                lines.append(f"- `{key}` -> {members}")
        lines.append("")
    DUPLICATE_REPORT.write_text("\n".join(lines), encoding="utf-8")


def write_identity_report(stats: dict, schema: dict[str, set[str]]) -> None:
    lines = [
        "# Identity Population Report",
        "",
        "## Actual Schema Used",
        "",
    ]
    for table, table_columns in schema.items():
        lines.append(f"- `{table}`: {', '.join(sorted(table_columns))}")
    lines.extend(["", "## Summary", "", "| Metric | Count |", "| --- | ---: |"])
    for key, value in stats.items():
        lines.append(f"| {key.replace('_', ' ')} | {value} |")
    IDENTITY_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--pubchem-delay", type=float, default=0.2)
    parser.add_argument("--skip-pubchem", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    unresolved = []
    descriptor_failures = []
    stats = {
        "materials_seen": 0,
        "materials_pubchem_resolved": 0,
        "identity_fields_updated": 0,
        "synonyms_inserted": 0,
        "descriptors_written": 0,
        "descriptor_failures": 0,
        "similarity_pairs": 0,
    }

    libs = import_descriptor_libraries()
    with sqlite3.connect(args.db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        schema = require_schema(conn)
        material_columns = schema["materials"]
        descriptor_columns = schema["chemical_descriptors"]
        ensure_similarity_table(conn)

        materials = conn.execute("SELECT * FROM materials ORDER BY material_id").fetchall()
        stats["materials_seen"] = len(materials)

        if not args.skip_pubchem:
            for material in materials:
                needs_identity = any(
                    column in material_columns and material[column] in (None, "")
                    for column in IDENTITY_COLUMNS
                )
                if not needs_identity:
                    continue
                pubchem = fetch_pubchem(material["name"])
                if pubchem is None:
                    unresolved.append(
                        {
                            "material_id": material["material_id"],
                            "name": material["name"],
                            "reason": "no PubChem match",
                        }
                    )
                    time.sleep(args.pubchem_delay)
                    continue
                updated = update_material_identity(conn, material, pubchem, material_columns)
                stats["identity_fields_updated"] += len(updated)
                stats["synonyms_inserted"] += insert_synonyms(
                    conn,
                    material["material_id"],
                    pubchem.get("Synonyms", []),
                )
                stats["materials_pubchem_resolved"] += 1
                time.sleep(args.pubchem_delay)

        refreshed = conn.execute("SELECT * FROM materials ORDER BY material_id").fetchall()
        for material in refreshed:
            smiles = material["smiles"] if "smiles" in material_columns else None
            if not smiles:
                descriptor_failures.append(
                    {
                        "material_id": material["material_id"],
                        "name": material["name"],
                        "reason": "missing SMILES",
                    }
                )
                continue
            descriptor, reason = compute_descriptor(smiles, libs)
            if descriptor is None:
                descriptor_failures.append(
                    {
                        "material_id": material["material_id"],
                        "name": material["name"],
                        "reason": reason,
                    }
                )
                continue
            upsert_descriptor(conn, material["material_id"], descriptor, descriptor_columns)
            stats["descriptors_written"] += 1

        stats["descriptor_failures"] = len(descriptor_failures)
        stats["similarity_pairs"] = populate_similarity(conn, libs)
        conn.commit()
        write_duplicate_report(conn, material_columns)

    write_csv(UNRESOLVED_CSV, ["material_id", "name", "reason"], unresolved)
    write_csv(DESCRIPTOR_FAILURES_CSV, ["material_id", "name", "reason"], descriptor_failures)
    write_identity_report(stats, schema)
    print(f"Wrote {IDENTITY_REPORT}")
    print(f"Wrote {UNRESOLVED_CSV}")
    print(f"Wrote {DESCRIPTOR_FAILURES_CSV}")
    print(f"Wrote {DUPLICATE_REPORT}")


if __name__ == "__main__":
    main()
