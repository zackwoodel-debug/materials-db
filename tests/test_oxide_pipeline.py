"""Tests for the 50-oxide pipeline (scripts/build_oxides_csv.py, load_oxides_db.py).

Covers the four cases called out in OXIDE_TASK.md Step 4:
  1. a malformed API response gets quarantined (never treated as valid)
  2. a duplicate InChIKey doesn't overwrite a row
  3. a failed batch leaves the DB unchanged (transaction rollback)
  4. no RI.info data is truncated (row counts match the source YAML)
"""

import json
import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import build_oxides_csv as pipeline  # noqa: E402
import load_oxides_db as loader  # noqa: E402

SCHEMA_SQL = (ROOT / "updated_sql_schema.sql").read_text()


# ---------------------------------------------------------------------------
# 1. Malformed API response -> quarantined, never used as valid
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text or json.dumps(json_data or {})

    def json(self):
        return self._json


def test_malformed_pubchem_cid_response_is_quarantined(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "RAW_CACHE", tmp_path / "raw_cache")
    monkeypatch.setattr(pipeline, "QUARANTINE", tmp_path / "quarantine")
    pipeline.ensure_dirs()

    # 200 OK but missing the expected IdentifierList/CID structure entirely.
    monkeypatch.setattr(pipeline.requests, "get", lambda *a, **k: _FakeResponse(200, json_data={"unexpected": "shape"}))
    monkeypatch.setattr(pipeline.time, "sleep", lambda *_: None)

    mat = dict(idx=1, name="Test material", formula="XxYy", pubchem_name="Nonexistent Test Compound")
    result = pipeline.fetch_pubchem(mat)

    assert result["pubchem_cid"] is None
    assert result["molecular_weight"] is None
    assert any("quarantined" in f for f in result["flags"])

    quarantine_files = list((tmp_path / "quarantine" / "pubchem").glob("*.json"))
    assert len(quarantine_files) == 1
    payload = json.loads(quarantine_files[0].read_text())
    assert "reason" in payload and "malformed" in payload["reason"]
    assert payload["payload"] == {"unexpected": "shape"}


def test_rate_limited_pubchem_response_is_quarantined_not_treated_as_success(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "RAW_CACHE", tmp_path / "raw_cache")
    monkeypatch.setattr(pipeline, "QUARANTINE", tmp_path / "quarantine")
    pipeline.ensure_dirs()

    monkeypatch.setattr(pipeline.requests, "get", lambda *a, **k: _FakeResponse(429, text="Too Many Requests"))
    monkeypatch.setattr(pipeline.time, "sleep", lambda *_: None)

    mat = dict(idx=2, name="Test material 2", formula="AaBb", pubchem_name="Another Test Compound")
    result = pipeline.fetch_pubchem(mat)

    assert result["pubchem_cid"] is None
    assert any("rate-limited" in f and "quarantined" in f for f in result["flags"])
    assert (tmp_path / "quarantine" / "pubchem").glob("*.json")


def test_rate_limited_cas_lookup_is_quarantined_not_silently_dropped(tmp_path, monkeypatch):
    """Regression test: a 429 specifically on the third (CAS/PUG-View) request
    used to be silently swallowed -- cid/formula/mw came back fine but
    cas_number just went NULL with no flag and no quarantine entry, making a
    transient rate-limit indistinguishable from 'this compound has no CAS on
    file'. Caught by diffing two full pipeline runs (BeO/Cu2O/LiIO3 lost
    their CAS between runs with no explanation)."""
    monkeypatch.setattr(pipeline, "RAW_CACHE", tmp_path / "raw_cache")
    monkeypatch.setattr(pipeline, "QUARANTINE", tmp_path / "quarantine")
    pipeline.ensure_dirs()
    monkeypatch.setattr(pipeline.time, "sleep", lambda *_: None)

    call_n = {"n": 0}

    def fake_get(url, *a, **k):
        call_n["n"] += 1
        if call_n["n"] == 1:
            return _FakeResponse(200, json_data={"IdentifierList": {"CID": [42]}})
        if call_n["n"] == 2:
            return _FakeResponse(200, json_data={"PropertyTable": {"Properties": [
                {"CID": 42, "MolecularFormula": "BeO", "MolecularWeight": "25.01",
                 "SMILES": "[Be]=O", "InChIKey": "TESTKEY-UHFFFAOYSA-N"}]}})
        return _FakeResponse(429, text="Too Many Requests")  # the CAS/PUG-View call

    monkeypatch.setattr(pipeline.requests, "get", fake_get)

    mat = dict(idx=1, name="Beryllium oxide", formula="BeO", pubchem_name="Beryllium oxide")
    result = pipeline.fetch_pubchem(mat)

    assert result["pubchem_cid"] == 42
    assert result["cas_number"] is None
    assert any("CAS" in f and "quarantined" in f for f in result["flags"]), result["flags"]
    assert list((tmp_path / "quarantine" / "pubchem").glob("*cas*.json"))


# ---------------------------------------------------------------------------
# 2. Duplicate InChIKey doesn't overwrite a row
# ---------------------------------------------------------------------------

def test_duplicate_inchikey_rejected_not_silently_overwritten(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)

    conn.execute(
        "INSERT INTO materials (name, formula, inchikey, pubchem_cid) VALUES (?, ?, ?, ?)",
        ("Original Material", "Al2O3", "PNEYBMLMFCGWSK-UHFFFAOYSA-N", 9989226),
    )
    conn.commit()

    # A second, different material accidentally sharing the same InChIKey
    # (e.g. two polymorphs of the same compound -- InChIKey is blind to
    # solid-state polymorphism) must be rejected, not silently replace row 1.
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO materials (name, formula, inchikey, pubchem_cid) VALUES (?, ?, ?, ?)",
            ("Impostor Material", "Al2O3", "PNEYBMLMFCGWSK-UHFFFAOYSA-N", 12345),
        )
    conn.rollback()

    rows = conn.execute("SELECT name, pubchem_cid FROM materials WHERE inchikey = ?",
                         ("PNEYBMLMFCGWSK-UHFFFAOYSA-N",)).fetchall()
    assert len(rows) == 1
    assert rows[0] == ("Original Material", 9989226)
    conn.close()


def test_multiple_null_inchikeys_are_allowed(tmp_path):
    """Materials with no PubChem match (NULL inchikey) must not collide with
    each other under the UNIQUE constraint -- SQLite treats NULLs as distinct."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)

    conn.execute("INSERT INTO materials (name, formula, inchikey) VALUES (?, ?, NULL)", ("Mat A", "AaOb"))
    conn.execute("INSERT INTO materials (name, formula, inchikey) VALUES (?, ?, NULL)", ("Mat B", "CcOd"))
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 2
    conn.close()


# ---------------------------------------------------------------------------
# 3. A failed batch leaves the DB unchanged
# ---------------------------------------------------------------------------

def test_failed_load_rolls_back_entire_transaction(tmp_path, monkeypatch):
    test_db = tmp_path / "materials_oxide_test.db"
    monkeypatch.setattr(loader, "DB_PATH", test_db)

    call_count = {"n": 0}
    real_load_physical_properties = loader.load_physical_properties

    def flaky_load_physical_properties(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise RuntimeError("simulated failure partway through the batch")
        return real_load_physical_properties(*args, **kwargs)

    monkeypatch.setattr(loader, "load_physical_properties", flaky_load_physical_properties)

    with pytest.raises(RuntimeError, match="simulated failure"):
        loader.main()

    assert test_db.exists()
    conn = sqlite3.connect(str(test_db))
    for table in ["materials", "physical_properties", "optical_dispersion", "sources"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count == 0, f"{table} has {count} rows after a failed load -- transaction did not roll back"
    conn.close()


# ---------------------------------------------------------------------------
# 4. No RI.info data is truncated (row counts match the source YAML), for
#    every dataset actually loaded -- not just Ta2O5.
# ---------------------------------------------------------------------------

SELECTIONS = json.loads((ROOT / "data" / "step1_selections.json").read_text())
RI_DATA_ROOT = ROOT / "refractiveindex_db" / "database" / "data"

# every unique RI.info data_path used by at least one of the 50 materials
ALL_DATASET_PATHS = sorted({
    axis["data_path"]
    for sel in SELECTIONS.values()
    for axis in sel["axes"]
})


def _count_block_lines(block: dict) -> int:
    return len([l for l in block["data"].strip().splitlines() if l.strip()])


def _expected_point_count(yaml_path: Path) -> int:
    """Number of wavelength points parse_file() should produce for this file.

    Only blocks that define the *n* grid count towards the total: 'tabulated
    n' and 'tabulated nk' contribute their own row count; 'formula*' blocks
    contribute exactly N_FORMULA (500) samples each (parse_file's fixed
    sampling density) since our widened WL_MIN_NM/WL_MAX_NM window no longer
    clips any real dataset's native range. A 'tabulated k'-only block (e.g.
    SiO's Hass.yml, which reports n and k as two separately-sized tables)
    contributes nothing to the count -- k gets interpolated onto the n grid,
    it doesn't add rows of its own.
    """
    raw = yaml.safe_load(open(yaml_path))
    total = 0
    for block in raw["DATA"]:
        t = block.get("type", "")
        if t in ("tabulated n", "tabulated nk"):
            total += _count_block_lines(block)
        elif t.startswith("formula"):
            total += _fetch_optical_data_n_formula()
    return total


def _fetch_optical_data_n_formula() -> int:
    from materials_db.pipeline.fetch_optical_data import N_FORMULA
    return N_FORMULA


@pytest.mark.parametrize("data_path", ALL_DATASET_PATHS, ids=ALL_DATASET_PATHS)
def test_ri_info_data_not_truncated_by_parser(data_path):
    """For every RI.info dataset actually selected in Step 1, the parser must
    produce exactly as many wavelength points as the source YAML defines."""
    yaml_path = RI_DATA_ROOT / data_path
    expected = _expected_point_count(yaml_path)

    wl_nm, n_val, k_val, refs, temp = pipeline.parse_file(yaml_path)

    assert len(wl_nm) == expected, f"{data_path}: parser produced {len(wl_nm)} points, source YAML implies {expected}"


@pytest.mark.skipif(not (ROOT / "data" / "materials_oxide_test.db").exists(),
                     reason="requires data/materials_oxide_test.db from Step 3 to already be built")
@pytest.mark.parametrize("data_path", ALL_DATASET_PATHS, ids=ALL_DATASET_PATHS)
def test_ri_info_data_not_truncated_in_loaded_db(data_path):
    """Same check against the actually-loaded DB rows for every dataset."""
    yaml_path = RI_DATA_ROOT / data_path
    expected = _expected_point_count(yaml_path)

    conn = sqlite3.connect(str(ROOT / "data" / "materials_oxide_test.db"))
    actual = conn.execute(
        "SELECT COUNT(*) FROM optical_dispersion WHERE raw_record_table = ?", (data_path,)
    ).fetchone()[0]
    conn.close()

    assert actual == expected, f"{data_path}: DB has {actual} rows, source YAML implies {expected}"


def test_all_datasets_have_at_least_one_n_or_nk_block():
    """Sanity guard on the fixture list itself: every dataset used must have
    a block type the parser and this test's counting logic both recognize,
    so a silent 0-vs-0 pass can't hide a genuinely unhandled block type."""
    for data_path in ALL_DATASET_PATHS:
        raw = yaml.safe_load(open(RI_DATA_ROOT / data_path))
        types = [b.get("type", "") for b in raw["DATA"]]
        recognized = any(t in ("tabulated n", "tabulated nk") or t.startswith("formula") for t in types)
        assert recognized, f"{data_path}: no recognized n-contributing block type in {types}"
