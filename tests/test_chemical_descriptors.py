"""Tests for chemical descriptor population."""

import json
import math
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "materials_normalized.db"
REPORTS_DIR = ROOT / "reports"

import sys
sys.path.insert(0, str(ROOT / "scripts"))

from populate_chemical_descriptors import (
    rdkit_descriptors,
    migrate_from_legacy,
    missing_fields,
    LEGACY_NAME_MAP,
    TARGET_FIELDS,
)


# ---------------------------------------------------------------------------
# Unit tests — pure functions
# ---------------------------------------------------------------------------

class TestRDKitDescriptors:
    def test_ethanol(self):
        d = rdkit_descriptors("CCO")
        assert d is not None
        assert d["heavy_atom_count"] == 3
        assert d["hbond_donors"] == 1
        assert d["hbond_acceptors"] == 1
        assert d["rotatable_bonds"] == 0
        assert d["aromatic_rings"] == 0
        assert d["exact_mass"] == pytest.approx(46.041865, abs=1e-4)
        assert d["tpsa"] == pytest.approx(20.23, abs=0.1)
        assert d["morgan_fp"] is not None
        assert len(d["morgan_fp"]) == 2048
        assert d["source"] == "rdkit"

    def test_benzene_aromatic(self):
        d = rdkit_descriptors("c1ccccc1")
        assert d is not None
        assert d["aromatic_rings"] == 1
        assert d["heavy_atom_count"] == 6
        assert d["hbond_donors"] == 0

    def test_gold_single_atom(self):
        d = rdkit_descriptors("[Au]")
        assert d is not None
        assert d["heavy_atom_count"] == 1
        assert d["rotatable_bonds"] == 0
        assert d["aromatic_rings"] == 0

    def test_invalid_smiles_returns_none(self):
        assert rdkit_descriptors("not_a_smiles!!!") is None
        assert rdkit_descriptors("") is None
        assert rdkit_descriptors("   ") is None
        assert rdkit_descriptors("C#####C") is None

    def test_morgan_fp_is_bit_string(self):
        d = rdkit_descriptors("CCO")
        assert all(c in "01" for c in d["morgan_fp"])

    def test_different_molecules_different_fps(self):
        fp1 = rdkit_descriptors("CCO")["morgan_fp"]
        fp2 = rdkit_descriptors("c1ccccc1")["morgan_fp"]
        assert fp1 != fp2

    def test_dppc_complexity(self):
        smiles = "CCCCCCCCCCCCCCCC(=O)OCC(COP(=O)([O-])OCC[N+](C)(C)C)OC(=O)CCCCCCCCCCCCCCC"
        d = rdkit_descriptors(smiles)
        assert d is not None
        assert d["heavy_atom_count"] == 50
        assert d["rotatable_bonds"] >= 30
        assert d["hbond_acceptors"] >= 6


class TestMigrateFromLegacy:
    SAMPLE_ROWS = [
        {"descriptor_name": "ExactMolWt", "value": 46.041865, "source_library": "RDKit"},
        {"descriptor_name": "TPSA", "value": 20.23, "source_library": "RDKit"},
        {"descriptor_name": "MolLogP", "value": -0.001, "source_library": "RDKit"},
        {"descriptor_name": "NumHeavyAtoms", "value": 3.0, "source_library": "RDKit"},
        {"descriptor_name": "NumRotatableBonds", "value": 0.0, "source_library": "RDKit"},
        {"descriptor_name": "NumHDonors", "value": 1.0, "source_library": "RDKit"},
        {"descriptor_name": "NumHAcceptors", "value": 1.0, "source_library": "RDKit"},
        {"descriptor_name": "NumAromaticRings", "value": 0.0, "source_library": "RDKit"},
    ]

    def test_basic_migration(self):
        result = migrate_from_legacy(self.SAMPLE_ROWS)
        assert result["exact_mass"] == pytest.approx(46.041865, abs=1e-5)
        assert result["tpsa"] == pytest.approx(20.23, abs=0.01)
        assert result["logp"] == pytest.approx(-0.001, abs=1e-4)
        assert result["heavy_atom_count"] == 3
        assert result["rotatable_bonds"] == 0
        assert result["hbond_donors"] == 1
        assert result["hbond_acceptors"] == 1
        assert result["aromatic_rings"] == 0
        assert result["source"] == "legacy_migration"

    def test_old_naming_convention(self):
        rows = [
            {"descriptor_name": "logP", "value": -0.82, "source_library": "RDKit"},
            {"descriptor_name": "exact_mass", "value": 18.011, "source_library": "RDKit"},
            {"descriptor_name": "h_bond_donors", "value": 1.0, "source_library": "RDKit"},
            {"descriptor_name": "h_bond_acceptors", "value": 1.0, "source_library": "RDKit"},
            {"descriptor_name": "rotatable_bonds", "value": 0.0, "source_library": "RDKit"},
            {"descriptor_name": "TPSA", "value": 31.5, "source_library": "RDKit"},
        ]
        result = migrate_from_legacy(rows)
        assert result["logp"] == pytest.approx(-0.82, abs=1e-4)
        assert result["exact_mass"] == pytest.approx(18.011, abs=1e-4)
        assert result["hbond_donors"] == 1
        assert result["hbond_acceptors"] == 1

    def test_empty_rows_returns_empty(self):
        result = migrate_from_legacy([])
        assert result == {}

    def test_unknown_descriptors_ignored(self):
        rows = [
            {"descriptor_name": "SomeUnknownProp", "value": 99.0, "source_library": "X"},
            {"descriptor_name": "BertzCT", "value": 55.6, "source_library": "RDKit"},
        ]
        result = migrate_from_legacy(rows)
        # Neither maps to chemical_descriptors columns
        assert "SomeUnknownProp" not in result
        assert "BertzCT" not in result

    def test_integer_coercion(self):
        rows = [
            {"descriptor_name": "NumHeavyAtoms", "value": 6.0, "source_library": "RDKit"},
            {"descriptor_name": "NumAromaticRings", "value": 1.0, "source_library": "RDKit"},
        ]
        result = migrate_from_legacy(rows)
        assert isinstance(result["heavy_atom_count"], int)
        assert isinstance(result["aromatic_rings"], int)

    def test_null_value_skipped(self):
        rows = [{"descriptor_name": "TPSA", "value": None, "source_library": "RDKit"}]
        result = migrate_from_legacy(rows)
        assert "tpsa" not in result


class TestMissingFields:
    def test_full_dict(self):
        d = {f: 1.0 for f in TARGET_FIELDS}
        assert missing_fields(d) == []

    def test_all_missing(self):
        assert set(missing_fields({})) == set(TARGET_FIELDS)

    def test_partial(self):
        d = {"exact_mass": 18.0, "tpsa": 31.5}
        result = missing_fields(d)
        assert "exact_mass" not in result
        assert "tpsa" not in result
        assert "logp" in result

    def test_none_value_counts_as_missing(self):
        d = {f: 1.0 for f in TARGET_FIELDS}
        d["logp"] = None
        assert "logp" in missing_fields(d)


class TestLegacyNameMap:
    def test_all_new_names_covered(self):
        new_names = [
            "ExactMolWt", "TPSA", "MolLogP", "NumHeavyAtoms",
            "NumRotatableBonds", "NumHDonors", "NumHAcceptors", "NumAromaticRings"
        ]
        for name in new_names:
            assert name in LEGACY_NAME_MAP, f"{name!r} missing from LEGACY_NAME_MAP"

    def test_all_old_names_covered(self):
        old_names = [
            "exact_mass", "logP", "h_bond_donors",
            "h_bond_acceptors", "rotatable_bonds"
        ]
        for name in old_names:
            assert name in LEGACY_NAME_MAP, f"{name!r} missing from LEGACY_NAME_MAP"


# ---------------------------------------------------------------------------
# Integration tests — require live DB
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def con():
    if not DB_PATH.exists():
        pytest.skip(f"DB not found: {DB_PATH}")
    c = sqlite3.connect(DB_PATH)
    yield c
    c.close()


class TestChemicalDescriptorsTable:
    def test_table_fully_populated(self, con):
        n = con.execute("SELECT COUNT(*) FROM chemical_descriptors").fetchone()[0]
        total = con.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        assert n == total, f"Expected {total} rows, got {n}"

    def test_rdkit_materials_fully_filled(self, con):
        """All materials with SMILES should have all 8 descriptor fields non-null."""
        rows = con.execute("""
            SELECT m.material_id, m.name, cd.exact_mass, cd.tpsa, cd.logp,
                   cd.heavy_atom_count, cd.rotatable_bonds, cd.hbond_donors,
                   cd.hbond_acceptors, cd.aromatic_rings, cd.morgan_fp
            FROM materials m
            JOIN chemical_descriptors cd ON cd.material_id = m.material_id
            WHERE m.smiles IS NOT NULL AND m.smiles != ''
        """).fetchall()
        assert len(rows) > 0
        for row in rows:
            mid, name = row[0], row[1]
            vals = row[2:]
            assert all(v is not None for v in vals), (
                f"material_id={mid} ({name}) has NULL in descriptor despite valid SMILES: {vals}"
            )

    def test_morgan_fp_format(self, con):
        fps = con.execute(
            "SELECT material_id, morgan_fp FROM chemical_descriptors WHERE morgan_fp IS NOT NULL"
        ).fetchall()
        assert len(fps) >= 15
        for mid, fp in fps:
            assert len(fp) == 2048, f"material_id={mid}: FP length {len(fp)} != 2048"
            assert all(c in "01" for c in fp), f"material_id={mid}: FP contains non-bit characters"

    def test_ethanol_known_values(self, con):
        row = con.execute("""
            SELECT cd.exact_mass, cd.tpsa, cd.heavy_atom_count, cd.hbond_donors,
                   cd.hbond_acceptors, cd.rotatable_bonds, cd.aromatic_rings
            FROM chemical_descriptors cd
            JOIN materials m ON m.material_id = cd.material_id
            WHERE m.name = 'Ethanol'
        """).fetchone()
        assert row is not None
        exact_mass, tpsa, hac, hbd, hba, rb, ar = row
        assert exact_mass == pytest.approx(46.041865, abs=1e-3)
        assert tpsa == pytest.approx(20.23, abs=0.1)
        assert hac == 3
        assert hbd == 1
        assert hba == 1
        assert rb == 0
        assert ar == 0

    def test_polystyrene_aromatic(self, con):
        row = con.execute("""
            SELECT cd.aromatic_rings FROM chemical_descriptors cd
            JOIN materials m ON m.material_id = cd.material_id
            WHERE m.name = 'Polystyrene'
        """).fetchone()
        assert row is not None
        assert row[0] >= 1

    def test_dppc_heavy_atoms(self, con):
        row = con.execute("""
            SELECT cd.heavy_atom_count, cd.rotatable_bonds, cd.hbond_acceptors
            FROM chemical_descriptors cd
            JOIN materials m ON m.material_id = cd.material_id
            WHERE m.name = 'DPPC'
        """).fetchone()
        assert row is not None
        hac, rb, hba = row
        assert hac == 50
        assert rb >= 30
        assert hba >= 6

    def test_descriptor_json_parseable(self, con):
        rows = con.execute(
            "SELECT material_id, descriptor_json FROM chemical_descriptors "
            "WHERE descriptor_json IS NOT NULL"
        ).fetchall()
        for mid, djson in rows:
            try:
                data = json.loads(djson)
                assert isinstance(data, dict), f"material_id={mid}: descriptor_json not a dict"
                assert "source" in data or "computed_at" in data
            except json.JSONDecodeError as e:
                pytest.fail(f"material_id={mid}: descriptor_json not valid JSON: {e}")

    def test_no_negative_counts(self, con):
        rows = con.execute("""
            SELECT material_id, heavy_atom_count, rotatable_bonds,
                   hbond_donors, hbond_acceptors, aromatic_rings
            FROM chemical_descriptors
        """).fetchall()
        for row in rows:
            mid = row[0]
            for val in row[1:]:
                if val is not None:
                    assert val >= 0, f"material_id={mid}: negative count {val}"

    def test_molecular_weight_sanity(self, con):
        # Exclude polymers where materials.molecular_weight stores the repeat-unit MW
        # while the SMILES may represent a larger oligomer/dimer structure.
        rows = con.execute("""
            SELECT m.material_id, m.name, m.formula, m.molecular_weight, cd.exact_mass
            FROM materials m
            JOIN chemical_descriptors cd ON cd.material_id = m.material_id
            WHERE m.molecular_weight IS NOT NULL
              AND cd.exact_mass IS NOT NULL
              AND m.smiles IS NOT NULL AND m.smiles != ''
              AND (m.formula NOT LIKE '%)n%' AND m.formula NOT LIKE '%(%)n%')
        """).fetchall()
        for mid, name, formula, mw, exact in rows:
            ratio = abs(exact - mw) / max(mw, 1.0)
            assert ratio < 0.05, (
                f"material_id={mid} ({name}, formula={formula}): "
                f"exact_mass={exact:.4f} deviates >5% from molecular_weight={mw}"
            )


class TestDescriptorFailuresTable:
    def test_table_exists(self, con):
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='descriptor_failures'"
        ).fetchone()
        assert row is not None

    def test_row_count_matches_materials(self, con):
        n_fail = con.execute("SELECT COUNT(*) FROM descriptor_failures").fetchone()[0]
        n_mat = con.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        assert n_fail == n_mat

    def test_successful_materials_have_empty_missing_fields(self, con):
        rows = con.execute(
            "SELECT material_id, missing_fields FROM descriptor_failures "
            "WHERE reason = 'ok'"
        ).fetchall()
        for mid, mf in rows:
            assert mf == "[]", f"material_id={mid}: reason=ok but missing_fields={mf!r}"

    def test_partial_fill_flag_consistent(self, con):
        rows = con.execute(
            "SELECT material_id, partial_fill, missing_fields FROM descriptor_failures"
        ).fetchall()
        for mid, pfill, mf in rows:
            parsed = json.loads(mf) if mf else []
            if pfill:
                assert parsed, f"material_id={mid}: partial_fill=1 but missing_fields is empty"
            else:
                assert not parsed, (
                    f"material_id={mid}: partial_fill=0 but missing_fields={parsed}"
                )

    def test_inorganic_partials_expected(self, con):
        """BSA, Al2O3, ZnO are legitimately partial — logP/aromatic_rings N/A."""
        for name in ("BSA", "Al2O3", "ZnO"):
            row = con.execute(
                "SELECT partial_fill, missing_fields FROM descriptor_failures "
                "WHERE material_name = ?", (name,)
            ).fetchone()
            assert row is not None, f"{name} not in descriptor_failures"
            pfill, mf = row
            assert pfill == 1, f"{name}: expected partial_fill=1"
            missing = json.loads(mf)
            assert "logp" in missing or "aromatic_rings" in missing, (
                f"{name}: unexpected missing fields: {missing}"
            )


class TestReportFiles:
    def test_descriptor_population_report_exists(self):
        p = REPORTS_DIR / "descriptor_population_report.md"
        assert p.exists(), "descriptor_population_report.md not found"
        content = p.read_text()
        assert "# Descriptor Population Report" in content
        assert "## Summary" in content
        assert "## Per-Material Descriptor Coverage" in content

    def test_unresolved_materials_csv_exists(self):
        p = REPORTS_DIR / "unresolved_materials.csv"
        assert p.exists(), "unresolved_materials.csv not found"
        lines = p.read_text().strip().splitlines()
        assert lines[0].startswith("material_id")

    def test_descriptor_failures_csv_exists(self):
        p = REPORTS_DIR / "descriptor_failures.csv"
        assert p.exists(), "descriptor_failures.csv not found"
        lines = p.read_text().strip().splitlines()
        assert lines[0].startswith("material_id")
        # One row per material
        assert len(lines) >= 24  # header + 23 materials
