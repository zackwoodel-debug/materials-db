"""Tests for the nitride pipeline (match_ri_info_nitrides.py, build_nitrides_csv.py, load_nitrides_db.py).

Mirrors tests/test_oxide_pipeline.py: (1) malformed/rate-limited API responses are quarantined, (2) a duplicate
InChIKey never overwrites a row, (3) a failed batch leaves the DB unchanged, (4) no RI.info data is truncated;
plus the nitride-specific integrity checks (materialclass, no fabricated rows, no auto-picked selections).
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_nitrides_csv as nit  # noqa: E402
import load_family_db as fam  # noqa: E402
import load_nitrides_db as loader  # noqa: E402
from nitride_material_list import CANDIDATES  # noqa: E402
from test_oxide_pipeline import _expected_point_count  # noqa: E402

base = nit.base  # build_oxides_csv (fetch_pubchem lives there)
DATA = ROOT / "data"
RI_DATA_ROOT = ROOT / "refractiveindex_db" / "database" / "data"
CSV = pd.read_csv(DATA / "nitrides.csv")
GAPS = pd.read_csv(DATA / "nitride_gaps.csv")
SELECTIONS = json.loads((DATA / "step1_selections_nitrides.json").read_text())
MATCHES = {m["selection_key"]: m for m in json.loads((DATA / "nitride_ri_matches.json").read_text())}
SELECTED_PATHS = sorted({a["data_path"] for s in SELECTIONS.values() if s for a in s["axes"]})


class _Resp:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code, self._json = status_code, json_data
        self.text = text or json.dumps(json_data or {})

    def json(self):
        return self._json


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "RAW_CACHE", tmp_path / "raw_cache")
    monkeypatch.setattr(base, "QUARANTINE", tmp_path / "quarantine")
    monkeypatch.setattr(base.time, "sleep", lambda *_: None)
    base.ensure_dirs()
    return tmp_path


# ---- 1. malformed / rate-limited responses are quarantined -------------------------------------------------

def test_malformed_pubchem_response_for_nitride_is_quarantined(isolated_cache, monkeypatch):
    monkeypatch.setattr(base.requests, "get", lambda *a, **k: _Resp(200, json_data={"unexpected": "shape"}))
    r = base.fetch_pubchem(dict(idx=4, name="Silicon nitride", formula="Si3N4", pubchem_name="Silicon nitride"))
    assert r["pubchem_cid"] is None and any("quarantined" in f for f in r["flags"])
    files = list((isolated_cache / "quarantine" / "pubchem").glob("*.json"))
    assert len(files) == 1 and "malformed" in json.loads(files[0].read_text())["reason"]


def test_rate_limited_pubchem_response_for_nitride_is_quarantined(isolated_cache, monkeypatch):
    monkeypatch.setattr(base.requests, "get", lambda *a, **k: _Resp(429, text="Too Many Requests"))
    r = base.fetch_pubchem(dict(idx=4, name="Silicon nitride", formula="Si3N4", pubchem_name="Silicon nitride"))
    assert r["pubchem_cid"] is None and any("rate-limited" in f and "quarantined" in f for f in r["flags"])


def test_mp_failure_for_si3n4_is_quarantined_and_leaves_calculated_values_null(isolated_cache, monkeypatch):
    monkeypatch.setattr(base.requests, "get", lambda *a, **k: _Resp(200, json_data={"unexpected": "shape"}))
    monkeypatch.delenv("MP_API_KEY", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    c = next(c for c in CANDIDATES if c["formula"] == "Si3N4")
    row = nit.si3n4_row(c, MATCHES["Si3N4"])
    for col in ("mp_id", "density_g_cm3", "xray_sld_real", "neutron_sld_real"):
        assert pd.isna(row.get(col)), f"{col} must stay NULL (never fabricated) when MP is unavailable"
    assert "MP evidence query failed" in row["flags"]
    assert list((isolated_cache / "quarantine" / "mp").glob("*.json"))


# ---- 2. duplicate InChIKey never overwrites -------------------------------------------------------------------

def test_cubic_and_hex_bn_with_same_inchikey_are_rejected_not_merged(tmp_path):
    rows = [dict(name="BN cubic", formula="BN", selection_key="BN-cubic", inchikey="PZNSFCLAULLKQX-UHFFFAOYSA-N"),
            dict(name="BN hex", formula="BN", selection_key="BN-hex", inchikey="PZNSFCLAULLKQX-UHFFFAOYSA-N")]
    p = tmp_path / "bn.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    with pytest.raises(fam.CatalogError, match="duplicate inchikey"):
        fam.load_catalog(p)


def test_nitride_load_never_overwrites_existing_inchikey(tmp_path):
    db = tmp_path / "n.db"
    cat = tmp_path / "c.csv"
    pd.DataFrame([dict(name="Aluminium nitride", formula="AlN", inchikey="MNWBNISUBARLIT-UHFFFAOYSA-N")]).to_csv(cat, index=False)
    sel = tmp_path / "s.json"
    sel.write_text("{}")
    fam.run_family("nitride", cat, sel, db)
    cat2 = tmp_path / "c2.csv"
    pd.DataFrame([dict(name="Impostor", formula="AlN", inchikey="MNWBNISUBARLIT-UHFFFAOYSA-N")]).to_csv(cat2, index=False)
    rep = fam.run_family("nitride", cat2, sel, db)
    conn = sqlite3.connect(str(db))
    assert [r[0] for r in conn.execute("SELECT name FROM materials")] == ["Aluminium nitride"]
    conn.close()
    assert rep.conflicts[0]["kind"] == "duplicate_inchikey"


# ---- 3. a failed batch leaves the DB unchanged ---------------------------------------------------------------

def test_failed_nitride_load_rolls_back_entire_transaction(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "DB_PATH", tmp_path / "materials_nitride_test.db")
    n = {"i": 0}
    real = loader.load_physical_properties

    def flaky(*a, **k):
        n["i"] += 1
        if n["i"] == 3:
            raise RuntimeError("simulated failure partway through the batch")
        return real(*a, **k)

    monkeypatch.setattr(loader, "load_physical_properties", flaky)
    with pytest.raises(RuntimeError, match="simulated failure"):
        loader.main()
    conn = sqlite3.connect(str(tmp_path / "materials_nitride_test.db"))
    for t in ("materials", "physical_properties", "optical_dispersion", "sources"):
        assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
    conn.close()


# ---- 4. no RI.info data truncated -----------------------------------------------------------------------------

@pytest.mark.parametrize("data_path", SELECTED_PATHS, ids=SELECTED_PATHS)
def test_ri_info_data_not_truncated_by_parser(data_path):
    wl, *_ = base.parse_file(RI_DATA_ROOT / data_path)
    assert len(wl) == _expected_point_count(RI_DATA_ROOT / data_path)


@pytest.fixture(scope="module")
def loaded_db(tmp_path_factory):
    db = tmp_path_factory.mktemp("nit") / "materials_nitride_test.db"
    rep = fam.run_family("nitride", loader.CSV_PATH, loader.SELECTIONS_PATH, db, fresh=True,
                         load_physical_fn=fam.load_physical_properties)
    return db, rep


@pytest.mark.parametrize("data_path", SELECTED_PATHS, ids=SELECTED_PATHS)
def test_ri_info_data_not_truncated_in_loaded_db(loaded_db, data_path):
    conn = sqlite3.connect(str(loaded_db[0]))
    got = conn.execute("SELECT COUNT(*) FROM optical_dispersion WHERE raw_record_table=?", (data_path,)).fetchone()[0]
    conn.close()
    assert got == _expected_point_count(RI_DATA_ROOT / data_path)


# ---- nitride-specific integrity ------------------------------------------------------------------------------

def test_every_nitride_row_has_materialclass_nitride():
    assert len(CSV) == 6 and (CSV["materialclass"] == "nitride").all()


def test_csv_and_missing_gaps_partition_the_candidates_with_no_overlap():
    cand = {c["selection_key"] for c in CANDIDATES}
    missing_gaps = set(GAPS["selection_key"]) & cand
    assert set(CSV["selection_key"]) | missing_gaps == cand
    assert not set(CSV["selection_key"]) & set(GAPS["selection_key"])
    assert len(missing_gaps) == 12 and len(GAPS) == 17 and GAPS["reason"].notna().all()


def test_gap_rows_are_really_missing_from_catalog_or_explicitly_excluded():
    excluded_pages = set(MATCHES["Si3N4"]["excluded_pages"])
    for _, g in GAPS.iterrows():
        if g["selection_key"] in MATCHES:
            assert MATCHES[g["selection_key"]]["status"] == "MISSING" and MATCHES[g["selection_key"]]["datasets"] == []
        else:  # a non-stoichiometric SiNx dataset that exists in the catalog but is deliberately not loaded
            assert g["formula"] == "SiNx" and "non-stoichiometric" in g["reason"]
            assert g["selection_key"].removeprefix("SiNx-") in excluded_pages
            assert g["ri_match"] not in SELECTED_PATHS
    assert excluded_pages == {"Kischkat", "Beliaev", "Vogt-1.91", "Vogt-2.09", "Vogt-2.13"}


def test_no_selection_is_auto_picked_for_multi_match():
    for k, m in MATCHES.items():
        if m["status"] == "MULTIPLE" and not (m["prior_selection"] or m["user_selection"]):
            assert SELECTIONS[k] is None, f"{k}: multi-match must be left null"


def test_si3n4_selection_is_exactly_luke_primary_then_philipp_amorphous_isotropic():
    axes = SELECTIONS["Si3N4"]["axes"]
    assert [a["page"] for a in axes] == ["Luke", "Philipp"]
    assert all(a["axis"] == "isotropic" and a["dataset_label"].startswith("amorphous | ") for a in axes)
    assert SELECTIONS["Si3N4"]["effective_polymorph"] == "amorphous"
    assert not {a["page"] for a in axes} & set(MATCHES["Si3N4"]["excluded_pages"])  # no SiNx page is ever loaded


def test_si3n4_physical_values_trace_to_mp_988_and_state_the_phase_mismatch():
    r = CSV[CSV["formula"] == "Si3N4"].iloc[0]
    assert r["mp_id"] == "mp-988" and r["polymorph"] == "beta" and r["density_source"] == "MP_DFT"
    assert r["mp_space_group"].startswith("P6_3/m") and r["mp_energy_above_hull_ev"] == 0.0
    assert r["axis_primary"] == "isotropic" and r["ri_page_primary"] == "Luke" and r["ri_page_axis2"] == "Philipp"
    note = "optical data is amorphous thin film; density/SLD are calculated for crystalline beta (mp-988). Not the same phase."
    assert note in r["flags"] and note in r["density_citation_notes"]
    assert "Calculated (DFT-derived), not measured" in r["density_citation_notes"]
    # SLDs are derived from exactly that density (independent recompute)
    sld = base.compute_sld("Si3N4", float(r["density_g_cm3"]))
    assert r["xray_sld_real"] == pytest.approx(sld["xray_sld_real"]) and r["neutron_sld_real"] == pytest.approx(sld["neutron_sld_real"])


def test_loaded_db_integrity(loaded_db):
    db, rep = loaded_db
    conn = sqlite3.connect(str(db))
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == 6
    assert conn.execute("SELECT COUNT(*) FROM optical_dispersion WHERE dataset_label IS NULL OR dataset_label='' "
                        "OR source_id IS NULL").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM physical_properties WHERE source_id IS NULL").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label, "
                        "wavelength_nm HAVING COUNT(*)>1)").fetchone()[0] == 0
    for n, k, wl in conn.execute("SELECT n, k, wavelength_nm FROM optical_dispersion"):
        assert n is not None and math.isfinite(n) and n >= 0 and wl > 0 and (k is None or math.isfinite(k))
    per_ds = dict(conn.execute("SELECT o.dataset_label, COUNT(*) FROM optical_dispersion o JOIN materials m USING(material_id) "
                               "WHERE m.formula='Si3N4' GROUP BY 1"))
    phys = conn.execute("SELECT p.dataset_label, s.technique FROM physical_properties p JOIN materials m USING(material_id) "
                        "JOIN sources s USING(source_id) WHERE m.formula='Si3N4'").fetchall()
    excluded = conn.execute("SELECT COUNT(*) FROM optical_dispersion WHERE raw_record_table LIKE '%Kischkat%' "
                            "OR raw_record_table LIKE '%Beliaev%' OR raw_record_table LIKE '%Vogt%'").fetchone()[0]
    assert conn.execute("SELECT COUNT(*) FROM materials WHERE formula='SiNx' OR name LIKE '%SiNx%'").fetchone()[0] == 0
    conn.close()
    assert per_ds == {"amorphous | Luke2015": 500, "amorphous | Philipp1973": 500}
    assert excluded == 0
    assert len(phys) == 5 and all(lbl.startswith("beta | ") for lbl, _ in phys)
    assert dict(phys)["beta | density_MP_DFT"] == "DFT (Materials Project)"
    assert rep.skipped == [] and rep.conflicts == []


def test_nitride_rerun_is_idempotent(loaded_db):
    db, _ = loaded_db
    conn = sqlite3.connect(str(db))
    before = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("materials", "physical_properties", "optical_dispersion", "sources")]
    conn.close()
    rep = fam.run_family("nitride", loader.CSV_PATH, loader.SELECTIONS_PATH, db, load_physical_fn=fam.load_physical_properties)
    conn = sqlite3.connect(str(db))
    after = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("materials", "physical_properties", "optical_dispersion", "sources")]
    conn.close()
    assert before == after and sum(rep.inserted.values()) == 0
