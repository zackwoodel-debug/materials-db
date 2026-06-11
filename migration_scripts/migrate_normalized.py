#!/usr/bin/env python3
"""Create a normalized, provenance-aware copy of materials.db."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sqlite3
import statistics


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DB = ROOT / "data" / "materials.db"
DEFAULT_TARGET_DB = ROOT / "data" / "materials_normalized.db"
DEFAULT_SCHEMA = ROOT / "updated_sql_schema.sql"
DEFAULT_REPORT = ROOT / "migration_report.md"


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({quote_identifier(table)})")}


def has_table(conn: sqlite3.Connection, table: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table', 'view') AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


def select_rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return conn.execute(f"SELECT * FROM {quote_identifier(table)}").fetchall()


def apply_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    conn.executescript(schema_path.read_text(encoding="utf-8"))


def copy_legacy_tables(source_db: Path, target: sqlite3.Connection) -> int:
    target.execute("ATTACH DATABASE ? AS legacy_source", (str(source_db),))
    rows = target.execute(
        """
        SELECT name
        FROM legacy_source.sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    copied = 0
    for (table_name,) in rows:
        legacy_name = f"legacy_{table_name}"
        target.execute(f"DROP TABLE IF EXISTS {quote_identifier(legacy_name)}")
        target.execute(
            f"""
            CREATE TABLE {quote_identifier(legacy_name)} AS
            SELECT * FROM legacy_source.{quote_identifier(table_name)}
            """
        )
        copied += 1
    target.execute("DETACH DATABASE legacy_source")
    return copied


def make_source(conn: sqlite3.Connection, *, notes: str, technique: str | None = None) -> int:
    cursor = conn.execute(
        """
        INSERT INTO sources(notes, technique)
        VALUES(?, ?)
        """,
        (notes, technique),
    )
    return int(cursor.lastrowid)


def migrate_sources(source: sqlite3.Connection, target: sqlite3.Connection) -> dict[int, int]:
    source_map = {}
    if not has_table(source, "references_db"):
        source_map[-1] = make_source(target, notes="Migration fallback source")
        return source_map

    source_columns = columns(source, "references_db")
    for row in select_rows(source, "references_db"):
        old_id = row["id"] if "id" in source_columns else None
        notes = row["citation_text"] if "citation_text" in source_columns else None
        cursor = target.execute(
            """
            INSERT INTO sources(source_id, doi, title, url, notes)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                doi = excluded.doi,
                title = excluded.title,
                url = excluded.url,
                notes = excluded.notes
            """,
            (
                old_id,
                row["doi"] if "doi" in source_columns else None,
                notes,
                row["url"] if "url" in source_columns else None,
                notes,
            ),
        )
        source_map[int(old_id)] = int(old_id or cursor.lastrowid)

    if not source_map:
        source_map[-1] = make_source(target, notes="Migration fallback source")
    return source_map


def fallback_source_id(source_map: dict[int, int], target: sqlite3.Connection, label: str) -> int:
    key = -abs(hash(label) % 1_000_000_000)
    if key not in source_map:
        source_map[key] = make_source(
            target,
            notes=f"Migration fallback for legacy records without reference: {label}",
        )
    return source_map[key]


def normalize_materials(source: sqlite3.Connection, target: sqlite3.Connection) -> dict[int, int]:
    material_map = {}
    if not has_table(source, "materials"):
        return material_map

    source_columns = columns(source, "materials")
    for row in select_rows(source, "materials"):
        old_id = row["id"] if "id" in source_columns else row["material_id"]
        name = row["name"] if "name" in source_columns else f"material_{old_id}"
        target.execute(
            """
            INSERT INTO materials(
                material_id, name, formula, smiles, molecular_weight, pubchem_cid
            )
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(material_id) DO UPDATE SET
                name = excluded.name,
                formula = COALESCE(materials.formula, excluded.formula),
                smiles = COALESCE(materials.smiles, excluded.smiles),
                molecular_weight = COALESCE(materials.molecular_weight, excluded.molecular_weight),
                pubchem_cid = COALESCE(materials.pubchem_cid, excluded.pubchem_cid)
            """,
            (
                old_id,
                name,
                row["formula"] if "formula" in source_columns else None,
                row["smiles"] if "smiles" in source_columns else None,
                row["molecular_weight"] if "molecular_weight" in source_columns else None,
                row["pubchem_cid"] if "pubchem_cid" in source_columns else None,
            ),
        )
        material_map[int(old_id)] = int(old_id)

    if has_table(source, "pubchem_data"):
        pubchem_columns = columns(source, "pubchem_data")
        for row in select_rows(source, "pubchem_data"):
            name = row["material_name"] if "material_name" in pubchem_columns else None
            if not name:
                continue
            target.execute(
                """
                UPDATE materials
                SET smiles = COALESCE(smiles, ?),
                    formula = COALESCE(formula, ?),
                    molecular_weight = COALESCE(molecular_weight, ?)
                WHERE LOWER(name) = LOWER(?)
                """,
                (
                    row["SMILES"] if "SMILES" in pubchem_columns else None,
                    row["molecular_formula"] if "molecular_formula" in pubchem_columns else None,
                    row["MW"] if "MW" in pubchem_columns else None,
                    name,
                ),
            )
            existing = target.execute(
                "SELECT material_id FROM materials WHERE LOWER(name) = LOWER(?)", (name,)
            ).fetchone()
            if existing and name:
                target.execute(
                    "INSERT OR IGNORE INTO material_synonyms(material_id, synonym) VALUES(?, ?)",
                    (existing[0], name),
                )
    return material_map


def source_for_row(
    row: sqlite3.Row,
    row_columns: set[str],
    source_map: dict[int, int],
    target: sqlite3.Connection,
    label: str,
) -> int:
    reference_id = row["reference_id"] if "reference_id" in row_columns else None
    if reference_id is not None and int(reference_id) in source_map:
        return source_map[int(reference_id)]
    return fallback_source_id(source_map, target, label)


def migrate_optical(source: sqlite3.Connection, target: sqlite3.Connection, source_map: dict[int, int]) -> int:
    if not has_table(source, "optical_nk"):
        return 0
    row_columns = columns(source, "optical_nk")
    required = {"material_id", "wavelength_nm"}
    if not required.issubset(row_columns):
        return 0
    count = 0
    for row in select_rows(source, "optical_nk"):
        source_id = source_for_row(row, row_columns, source_map, target, "optical_nk")
        target.execute(
            """
            INSERT OR IGNORE INTO optical_dispersion(
                material_id, wavelength_nm, n, k, temperature_c, dataset_label,
                raw_record_table, raw_record_id, source_id
            )
            VALUES(?, ?, ?, ?, ?, ?, 'optical_nk', ?, ?)
            """,
            (
                row["material_id"],
                row["wavelength_nm"],
                row["n"] if "n" in row_columns else None,
                row["k"] if "k" in row_columns else None,
                row["temperature_C"] if "temperature_C" in row_columns else None,
                row["source_ref"] if "source_ref" in row_columns else "optical_nk",
                row["id"] if "id" in row_columns else None,
                source_id,
            ),
        )
        count += 1
    return count


def migrate_viscoelasticity(
    source: sqlite3.Connection, target: sqlite3.Connection, source_map: dict[int, int]
) -> tuple[int, int]:
    if not has_table(source, "viscoelasticity"):
        return 0, 0
    row_columns = columns(source, "viscoelasticity")
    mechanical_count = 0
    rheology_count = 0
    for row in select_rows(source, "viscoelasticity"):
        source_id = source_for_row(row, row_columns, source_map, target, "viscoelasticity")
        if {"storage_modulus_pa", "loss_modulus_pa", "frequency_hz", "temperature_C"}.issubset(row_columns):
            has_modulus = row["storage_modulus_pa"] is not None or row["loss_modulus_pa"] is not None
            if has_modulus and row["temperature_C"] is not None and row["frequency_hz"] is not None:
                target.execute(
                    """
                    INSERT OR IGNORE INTO mechanical_properties(
                        material_id, storage_modulus, loss_modulus, temperature_c,
                        frequency_hz, dataset_label, raw_record_table, raw_record_id, source_id
                    )
                    VALUES(?, ?, ?, ?, ?, 'viscoelasticity', 'viscoelasticity', ?, ?)
                    """,
                    (
                        row["material_id"],
                        row["storage_modulus_pa"],
                        row["loss_modulus_pa"],
                        row["temperature_C"],
                        row["frequency_hz"],
                        row["id"] if "id" in row_columns else None,
                        source_id,
                    ),
                )
                mechanical_count += 1
        if "viscosity_mpa_s" in row_columns and row["viscosity_mpa_s"] is not None:
            context_flag = None
            if "temperature_C" not in row_columns or row["temperature_C"] is None:
                context_flag = "missing_temperature"
            target.execute(
                """
                INSERT OR IGNORE INTO rheology(
                    material_id, viscosity_pas, shear_rate_s_inv, temperature_c,
                    context_flag, dataset_label, raw_record_table, raw_record_id, source_id
                )
                VALUES(?, ?, NULL, ?, ?, 'viscoelasticity', 'viscoelasticity', ?, ?)
                """,
                (
                    row["material_id"],
                    row["viscosity_mpa_s"] / 1000.0,
                    row["temperature_C"] if "temperature_C" in row_columns else None,
                    context_flag or "missing_shear_rate",
                    row["id"] if "id" in row_columns else None,
                    source_id,
                ),
            )
            rheology_count += 1
    return mechanical_count, rheology_count


def migrate_physical(source: sqlite3.Connection, target: sqlite3.Connection, source_map: dict[int, int]) -> int:
    count = 0
    if has_table(source, "materials") and "density_g_cm3" in columns(source, "materials"):
        for row in select_rows(source, "materials"):
            if row["density_g_cm3"] is None:
                continue
            source_id = fallback_source_id(source_map, target, "materials.density_g_cm3")
            target.execute(
                """
                INSERT OR IGNORE INTO physical_properties(
                    material_id, density_g_cm3, dataset_label, raw_record_table, raw_record_id, source_id
                )
                VALUES(?, ?, 'materials', 'materials', ?, ?)
                """,
                (row["id"], row["density_g_cm3"], row["id"], source_id),
            )
            count += 1

    mappings = [
        ("calculated_sld", "sld_xray_real", "sld_neutron_real"),
        ("calculated_slds", "xray_sld_real", "neutron_sld_real"),
    ]
    for table, xray_col, neutron_col in mappings:
        if not has_table(source, table):
            continue
        row_columns = columns(source, table)
        for row in select_rows(source, table):
            if xray_col not in row_columns and neutron_col not in row_columns:
                continue
            source_id = source_for_row(row, row_columns, source_map, target, table)
            target.execute(
                """
                INSERT OR IGNORE INTO physical_properties(
                    material_id, xray_sld, neutron_sld, temperature_c, energy_ev,
                    wavelength_nm, dataset_label, raw_record_table, raw_record_id, source_id
                )
                VALUES(?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["material_id"],
                    row[xray_col] if xray_col in row_columns else None,
                    row[neutron_col] if neutron_col in row_columns else None,
                    row["energy_ev"] if "energy_ev" in row_columns else None,
                    row["wavelength_nm"] if "wavelength_nm" in row_columns else None,
                    table,
                    table,
                    row["id"] if "id" in row_columns else None,
                    source_id,
                ),
            )
            count += 1

    dielectric_mappings = [
        ("dielectric", "dielectric_real"),
        ("dielectrics", "real_permittivity"),
    ]
    for table, dielectric_col in dielectric_mappings:
        if not has_table(source, table):
            continue
        row_columns = columns(source, table)
        if dielectric_col not in row_columns:
            continue
        for row in select_rows(source, table):
            source_id = source_for_row(row, row_columns, source_map, target, table)
            target.execute(
                """
                INSERT OR IGNORE INTO physical_properties(
                    material_id, dielectric_constant, temperature_c, frequency_hz,
                    wavelength_nm, energy_ev, dataset_label, raw_record_table, raw_record_id, source_id
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["material_id"],
                    row[dielectric_col],
                    row["temperature_C"] if "temperature_C" in row_columns else None,
                    row["frequency_hz"] if "frequency_hz" in row_columns else None,
                    row["wavelength_nm"] if "wavelength_nm" in row_columns else None,
                    row["energy_ev"] if "energy_ev" in row_columns else None,
                    table,
                    table,
                    row["id"] if "id" in row_columns else None,
                    source_id,
                ),
            )
            count += 1
    return count


def descriptor_from_smiles(smiles: str) -> tuple[dict, str | None]:
    try:
        from rdkit import Chem
        from rdkit.Chem import Crippen, Descriptors, rdFingerprintGenerator, rdMolDescriptors
    except ImportError:
        return {}, "RDKit not installed"

    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return {}, "invalid SMILES"

    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fingerprint = generator.GetFingerprint(molecule).ToBitString()
    descriptor = {
        "exact_mass": float(Descriptors.ExactMolWt(molecule)),
        "tpsa": float(rdMolDescriptors.CalcTPSA(molecule)),
        "logp": float(Crippen.MolLogP(molecule)),
        "heavy_atom_count": int(molecule.GetNumHeavyAtoms()),
        "rotatable_bonds": int(rdMolDescriptors.CalcNumRotatableBonds(molecule)),
        "hbond_donors": int(rdMolDescriptors.CalcNumHBD(molecule)),
        "hbond_acceptors": int(rdMolDescriptors.CalcNumHBA(molecule)),
        "aromatic_rings": int(rdMolDescriptors.CalcNumAromaticRings(molecule)),
        "descriptor_json": json.dumps(
            {
                "source": "RDKit",
                "canonical_smiles": Chem.MolToSmiles(molecule),
            },
            sort_keys=True,
        ),
        "morgan_fp": fingerprint,
    }
    return descriptor, None


def migrate_descriptors(target: sqlite3.Connection) -> tuple[int, list[str]]:
    inserted = 0
    skipped = []
    rows = target.execute("SELECT material_id, name, smiles FROM materials").fetchall()
    for material_id, name, smiles in rows:
        if not smiles:
            skipped.append(f"{name}: missing SMILES")
            continue
        descriptor, reason = descriptor_from_smiles(smiles)
        if not descriptor:
            skipped.append(f"{name}: {reason}")
            continue
        target.execute(
            """
            INSERT OR REPLACE INTO chemical_descriptors(
                material_id, exact_mass, tpsa, logp, heavy_atom_count,
                rotatable_bonds, hbond_donors, hbond_acceptors, aromatic_rings,
                descriptor_json, morgan_fp
            )
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                material_id,
                descriptor["exact_mass"],
                descriptor["tpsa"],
                descriptor["logp"],
                descriptor["heavy_atom_count"],
                descriptor["rotatable_bonds"],
                descriptor["hbond_donors"],
                descriptor["hbond_acceptors"],
                descriptor["aromatic_rings"],
                descriptor["descriptor_json"],
                descriptor["morgan_fp"],
            ),
        )
        inserted += 1
    return inserted, skipped


def robust_values(values: list[float]) -> list[float]:
    if len(values) < 4:
        return values
    median = statistics.median(values)
    deviations = [abs(value - median) for value in values]
    mad = statistics.median(deviations)
    if mad == 0:
        return values
    return [value for value in values if abs(value - median) / (1.4826 * mad) <= 3.5]


def classify(values: list[float]) -> tuple[str, float | None]:
    if len(values) < 2:
        return "single_source", None
    pair_errors = []
    for left_index, left in enumerate(values):
        for right in values[left_index + 1 :]:
            mean_value = (abs(left) + abs(right)) / 2.0
            if mean_value:
                pair_errors.append(abs(left - right) / mean_value)
    max_error = max(pair_errors) if pair_errors else 0.0
    if max_error < 0.05:
        return "excellent", max_error
    if max_error <= 0.10:
        return "warning", max_error
    return "suspicious", max_error


def compute_consensus(target: sqlite3.Connection) -> int:
    property_queries = {
        "density_g_cm3": "SELECT material_id, density_g_cm3 AS value, source_id FROM physical_properties WHERE density_g_cm3 IS NOT NULL",
        "xray_sld": "SELECT material_id, xray_sld AS value, source_id FROM physical_properties WHERE xray_sld IS NOT NULL",
        "neutron_sld": "SELECT material_id, neutron_sld AS value, source_id FROM physical_properties WHERE neutron_sld IS NOT NULL",
        "dielectric_constant": "SELECT material_id, dielectric_constant AS value, source_id FROM physical_properties WHERE dielectric_constant IS NOT NULL",
        "n": "SELECT material_id, n AS value, source_id FROM optical_dispersion WHERE n IS NOT NULL AND wavelength_nm BETWEEN 580 AND 700",
        "k": "SELECT material_id, k AS value, source_id FROM optical_dispersion WHERE k IS NOT NULL AND wavelength_nm BETWEEN 580 AND 700",
    }
    inserted = 0
    for property_name, query in property_queries.items():
        grouped: dict[int, list[tuple[float, int]]] = {}
        for material_id, value, source_id in target.execute(query).fetchall():
            if value is not None and math.isfinite(float(value)):
                grouped.setdefault(material_id, []).append((float(value), int(source_id)))
        for material_id, rows in grouped.items():
            values = robust_values([value for value, _source_id in rows])
            if not values:
                continue
            consensus = statistics.fmean(values)
            std_dev = statistics.stdev(values) if len(values) > 1 else 0.0
            num_sources = len({source_id for _value, source_id in rows})
            classification, max_error = classify(values)
            confidence = max(0.0, 1.0 - (max_error or 0.0))
            if num_sources == 1:
                confidence *= 0.5
            target.execute(
                """
                INSERT OR REPLACE INTO consensus_properties(
                    material_id, property_name, consensus_value, std_dev,
                    num_sources, confidence_score, classification
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_id,
                    property_name,
                    consensus,
                    std_dev,
                    num_sources,
                    confidence,
                    classification,
                ),
            )
            inserted += 1
    return inserted


def write_report(path: Path, stats: dict, skipped_descriptors: list[str]) -> None:
    lines = [
        "# Migration Report",
        "",
        "## Summary",
        "",
        "| Item | Count |",
        "| --- | ---: |",
    ]
    for key, value in stats.items():
        lines.append(f"| {key.replace('_', ' ')} | {value} |")
    lines.extend(["", "## Descriptor Skips", ""])
    if skipped_descriptors:
        for item in skipped_descriptors:
            lines.append(f"- {item}")
    else:
        lines.append("No descriptor skips.")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- The source database is not modified.",
            "- Raw legacy tables are copied into the normalized target with `legacy_` prefixes.",
            "- The migration writes a normalized database and does not delete existing measurements.",
            "- Legacy rows without a reference are assigned explicit fallback provenance rows in `sources`.",
            "- Viscosity rows migrated from `viscoelasticity` are flagged when shear rate is absent.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--replace", action="store_true", help="Replace an existing target DB.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.target_db.exists():
        if not args.replace:
            raise SystemExit(f"Target exists: {args.target_db}. Re-run with --replace.")
        args.target_db.unlink()

    stats = {}
    skipped_descriptors = []
    with sqlite3.connect(args.source_db) as source, sqlite3.connect(args.target_db) as target:
        source.row_factory = sqlite3.Row
        target.execute("PRAGMA foreign_keys = ON")
        apply_schema(target, args.schema)
        stats["legacy_tables_preserved"] = copy_legacy_tables(args.source_db, target)
        source_map = migrate_sources(source, target)
        material_map = normalize_materials(source, target)
        stats["materials"] = len(material_map)
        stats["optical_dispersion"] = migrate_optical(source, target, source_map)
        mechanical_count, rheology_count = migrate_viscoelasticity(source, target, source_map)
        stats["mechanical_properties"] = mechanical_count
        stats["rheology"] = rheology_count
        stats["physical_properties"] = migrate_physical(source, target, source_map)
        descriptor_count, skipped_descriptors = migrate_descriptors(target)
        stats["chemical_descriptors"] = descriptor_count
        stats["consensus_properties"] = compute_consensus(target)
        stats["sources"] = target.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        target.commit()

    write_report(args.report, stats, skipped_descriptors)
    print(f"Wrote {args.target_db}")
    print(f"Wrote {args.report}")


if __name__ == "__main__":
    main()
