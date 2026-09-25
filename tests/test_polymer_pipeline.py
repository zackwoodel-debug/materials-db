"""Loader-INDEPENDENT tests for the polymer family (catalog, selections, gaps, wavelength preservation).

Deliberately does not import scripts/load_family_db.py: that loader ships in PR #3 and is not on modalfit-export. Tests that need it
(NULL-formula load, idempotent load, source/dataset dedupe, zero descriptor rows in the loaded DB) are NOT here and NOT skipped-as-passed:
they are blocked until #3 merges. See the run report.
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import materials_db.pipeline.fetch_optical_data as fod  # noqa: E402
import polymer_material_list as pml  # noqa: E402

DATA = ROOT / "data"
RI = ROOT / "refractiveindex_db" / "database" / "data"
CAT = pd.read_csv(DATA / "polymers.csv")
GAPS = pd.read_csv(DATA / "polymer_gaps.csv")
SEL = json.loads((DATA / "step1_selections_polymers.json").read_text())
MATCHES = {c["key"]: c for c in json.loads((DATA / "polymer_ri_matches.json").read_text())["candidates"]}
DEFERRED = {"PS", "PMMA", "PDMS", "Kapton", "PVA"}
SELECTED = [(k, a) for k, v in SEL.items() if "axes" in v for a in v["axes"]]


# ---- catalog rules -----------------------------------------------------------------------------------------------

def test_catalog_is_14_polymers_all_materialclass_polymer():
    assert len(CAT) == 14 and (CAT["materialclass"] == "polymer").all() and CAT["abbreviation"].is_unique


def test_null_formula_is_valid_only_for_the_four_grade_materials_and_grade_lives_in_notes_not_a_column():
    assert "grade" not in CAT.columns, "the grade column was withdrawn (no schema change)"
    assert "grade" not in (ROOT / "updated_sql_schema.sql").read_text().lower(), "the schema of record must stay untouched"
    null_formula = CAT[CAT["formula"].isna()]
    assert set(null_formula["abbreviation"]) == {"COP-Zeonex-E48R", "Optorez-1330", "NAS-21", "SU-8"}
    expect = {"COP-Zeonex-E48R": "grade: Zeonex E48R", "Optorez-1330": "grade: Optorez 1330", "NAS-21": "grade: NAS-21", "SU-8": "grade: SU-8 3000"}
    assert dict(zip(null_formula["abbreviation"], null_formula["notes"])) == expect  # a single line each
    assert CAT[CAT["formula"].notna()]["notes"].isna().all()


def test_no_placeholder_formula_tokens():
    """A token like 'unspecified' would parse to an empty element-count dict and look like a plausible zero downstream."""
    for f in CAT["formula"].dropna():
        assert re.search(r"[A-Z][a-z]?\d*", f) and not re.search(r"unspec|unknown|n/a|tbd|none", f, re.I), f


def test_density_is_null_for_every_polymer_and_every_one_is_logged_as_a_density_gap():
    assert CAT["density_g_cm3"].isna().all() and CAT["density_source"].isna().all()
    dens = GAPS[GAPS["gap_kind"] == "density"]
    assert len(dens) == 19 and dens["reason"].str.contains("no traceable density source").all()
    assert set(CAT["abbreviation"]) | DEFERRED <= set(dens["key"])


# ---- scope decisions -------------------------------------------------------------------------------------------

def test_deferred_are_null_selection_flagged_with_reason_and_absent_from_catalog():
    for k in DEFERRED:
        assert SEL[k]["selection"] is None and SEL[k]["deferred"] is True and SEL[k]["reason"]
        assert "axes" not in SEL[k] and k not in set(CAT["abbreviation"])
        assert k in set(GAPS[GAPS["gap_kind"] == "deferred"]["key"])


def test_catalog_deferred_and_gaps_partition_the_70_candidate_pool_without_overlap():
    whole = set(GAPS[GAPS["gap_kind"] == "material"]["key"])
    cat = set(CAT["abbreviation"])
    assert len(cat) + len(DEFERRED) + len(whole) == 70 == len(pml.CANDIDATES)
    assert not cat & DEFERRED and not cat & whole and not DEFERRED & whole
    assert cat | DEFERRED | whole == {c["key"] for c in pml.CANDIDATES}


def _sultanova_n633():
    """n(633 nm) evaluated directly from the YAML Sellmeier-2 coefficients (denominator constants are already squared)."""
    b = yaml.safe_load(open(RI / PC_DIR / "Sultanova.yml"))["DATA"][0]
    assert b["type"] == "formula 2", "the evaluation below is only valid for RI.info formula 2"
    c = [float(x) for x in b["coefficients"].split()]
    lam2 = 0.633 ** 2
    return (1 + c[0] + sum(c[i] * lam2 / (lam2 - c[i + 1]) for i in range(1, len(c) - 1, 2))) ** 0.5


def _zhang_n633():
    """n(633 nm) by linear interpolation of the two bracketing SOURCE rows (never a rounded copy of a reported number)."""
    rows = [[float(x) for x in l.split()] for l in yaml.safe_load(open(RI / PC_DIR / "Zhang.yml"))["DATA"][0]["data"].strip().splitlines()]
    lo, hi = max(r for r in rows if r[0] <= 0.633), min(r for r in rows if r[0] >= 0.633)
    return lo[1] + (hi[1] - lo[1]) * (0.633 - lo[0]) / (hi[0] - lo[0])


PC_DIR = "organic/(C16H14O3)n - polycarbonate/nk"


def test_pc_is_zhang_only_on_one_row_and_sultanova_is_a_logged_exclusion():
    assert [a["page"] for a in SEL["PC"]["axes"]] == ["Zhang"] and len(CAT[CAT["abbreviation"] == "PC"]) == 1
    assert "Sultanova" not in json.dumps(SEL["PC"]["axes"]) and CAT[CAT["abbreviation"] == "PC"].iloc[0]["n_selected_datasets"] == 1
    ex = GAPS[GAPS["key"] == "PC:Sultanova"].iloc[0]
    assert ex["gap_kind"] == "excluded_dataset"
    assert ex["reason"] == "subset of Zhang range, disagrees ~0.4% at 633 nm, deferred to dataset-comparison PR"


def test_pc_exclusion_rationale_holds_against_the_source_data():
    """The exclusion reason is re-derived from source at test time: Sultanova is a subset of Zhang's range and they differ ~0.4% at 633 nm."""
    sult = next(d for d in MATCHES["PC"]["datasets"] if d["page"] == "Sultanova")["span_um"]
    zh = next(d for d in MATCHES["PC"]["datasets"] if d["page"] == "Zhang")["span_um"]
    assert zh[0] <= sult[0] and sult[1] <= zh[1], "Sultanova must lie entirely inside Zhang's range"
    ns, nz = _sultanova_n633(), _zhang_n633()
    assert 0.003 < abs(nz - ns) / ns < 0.005, f"expected ~0.4% disagreement, got {abs(nz - ns) / ns:.4%}"


def test_cellulose_is_sultanova_only_and_juntunen_is_a_logged_exclusion():
    assert [a["page"] for a in SEL["cellulose"]["axes"]] == ["Sultanova"]
    ex = GAPS[GAPS["key"] == "cellulose:Juntunen"].iloc[0]
    assert ex["gap_kind"] == "excluded_dataset" and "packing artifact" in ex["reason"]


def test_su8_is_the_3000_series_only_one_row_and_2000_is_a_logged_exclusion():
    (ax,) = SEL["SU-8"]["axes"]
    assert "SU-8 3000" in ax["data_path"] and "SU-8 2000" not in ax["data_path"] and len(CAT[CAT["abbreviation"] == "SU-8"]) == 1
    row = CAT[CAT["abbreviation"] == "SU-8"].iloc[0]
    assert row["n_selected_datasets"] == 1 and row["ri_book"] == "Microchem_SU8_3000" and row["notes"] == "grade: SU-8 3000"
    assert "uncured" in GAPS[GAPS["key"] == "SU-8:Microchem_SU8_2000"].iloc[0]["reason"].lower()


def test_cr39_is_a_tier3_gap_with_no_material_row_and_no_selection():
    g = GAPS[GAPS["key"] == "CR-39"].iloc[0]
    assert g["gap_kind"] == "material" and int(g["tier"]) == 3 and "single-point n only" in g["reason"]
    assert "CR-39" not in set(CAT["abbreviation"]) and "CR-39" not in SEL


def test_identity_flags_pei_collision_pla_is_pdla_ldpe_is_a_gap_not_llde_substitution():
    pei = CAT[CAT["abbreviation"] == "PEI"].iloc[0]
    assert pei["name"] == "Polyetherimide (PEI)" and "NAME COLLISION" in pei["flags"] and "polyethylenimine" in pei["flags"]
    pla = CAT[CAT["abbreviation"] == "PLA"].iloc[0]
    assert "PDLA" in pla["name"] and "PDLA" in pla["flags"]
    assert GAPS[GAPS["key"] == "PE-LDPE"].iloc[0]["gap_kind"] == "material" and "PE-LDPE" not in set(CAT["abbreviation"])
    assert not any("David" in json.dumps(v) for v in SEL.values()), "the LLDPE page must not be substituted for LDPE"


def test_no_selected_dataset_is_ambiguous_or_shared_between_materials():
    paths = [a["data_path"] for _, a in SELECTED]
    assert len(paths) == len(set(paths)) == 14  # 11 auto + PC (Zhang) + cellulose (Sultanova) + SU-8 3000 = 14 datasets on 14 materials
    assert all(a["dataset_label"] for _, a in SELECTED)
    assert not [k for k, m in MATCHES.items() if m["status"] == "MULTIPLE"], "an unresolved multi-match reached the selections"


# ---- selected wavelength ranges are preserved (loader window: 0.01 nm .. 2,000,000 nm, unchanged) -----------------

def _yaml_n_range_nm(path):
    d = yaml.safe_load(open(RI / path))
    spans = []
    for b in d["DATA"]:
        t = b.get("type", "")
        if t in ("tabulated n", "tabulated nk"):
            lam = [float(x.split()[0]) for x in b["data"].strip().splitlines() if x.strip()]
            spans.append((min(lam), max(lam)))
        elif t.startswith("formula"):
            v = [float(x) for x in str(b["wavelength_range"]).split()]
            spans.append((min(v), max(v)))
    return min(s[0] for s in spans) * 1000, max(s[1] for s in spans) * 1000


@pytest.mark.parametrize("key,axis", SELECTED, ids=[f"{k}:{a['page']}" for k, a in SELECTED])
def test_selected_wavelength_range_is_fully_preserved_by_the_parser(monkeypatch, key, axis):
    monkeypatch.setattr(fod, "WL_MIN_NM", 0.01)
    monkeypatch.setattr(fod, "WL_MAX_NM", 2_000_000.0)  # the existing loader window; deliberately NOT widened
    wl, n, *_ = fod.parse_file(RI / axis["data_path"])
    lo, hi = _yaml_n_range_nm(axis["data_path"])
    assert wl.min() == pytest.approx(lo, rel=1e-9) and wl.max() == pytest.approx(hi, rel=1e-9), f"{key}: range clipped"
    assert hi <= 2_000_000.0, "a selected dataset would exceed the loader window"


def test_no_selected_dataset_needs_the_wider_window_because_kapton_is_deferred():
    assert max(_yaml_n_range_nm(a["data_path"])[1] for _, a in SELECTED) < 2_000_000.0
    assert "Kapton" in DEFERRED
