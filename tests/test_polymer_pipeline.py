"""Loader-INDEPENDENT tests for the polymer family (catalog, selections, gaps, wavelength preservation).

Deliberately does not import scripts/load_family_db.py: that loader ships in PR #3 and is not on modalfit-export. Tests that need it
(NULL-formula load, idempotent load, source/dataset dedupe, zero descriptor rows in the loaded DB) are NOT here and NOT skipped-as-passed:
they are blocked until #3 merges. See the run report.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
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

def test_catalog_rows_and_the_three_classes_assigned_from_the_candidate_list():
    assert len(CAT) == 41 and CAT["abbreviation"].is_unique
    assert CAT["materialclass"].value_counts().to_dict() == {"polymer": 26, "photoresist": 9, "organic_semiconductor": 6}
    expect = {c["key"]: c["materialclass"] for c in pml.CANDIDATES}
    assert all(expect[r.abbreviation] == r.materialclass for r in CAT.itertuples())
    assert set(CAT[CAT.materialclass == "organic_semiconductor"].abbreviation) == {"MDMO-PPV", "ZZ50", "F8BT", "PTB7", "PDCBT", "PBDB-T-2F"}
    assert set(CAT[CAT.materialclass == "photoresist"].abbreviation) == {"SU-8", "maN-1407", "EpoClad", "EpoCore", "Microchem-8.5mEL", "IP-S", "IP-Dip",
                                                                                "PMMA-495-resist", "PMMA-950-resist"}


def test_null_formula_is_valid_only_for_the_grade_materials_and_grade_lives_in_notes_not_a_column():
    assert "grade" not in CAT.columns, "the grade column was withdrawn (no schema change)"
    assert "grade" not in (ROOT / "updated_sql_schema.sql").read_text().lower(), "the schema of record must stay untouched"
    null_formula = CAT[CAT["formula"].isna()]
    assert set(null_formula["abbreviation"]) == set(pml.GRADE_NOTES) and len(null_formula) == 13
    assert dict(zip(null_formula["abbreviation"], null_formula["notes"])) == {k: f"grade: {v}" for k, v in pml.GRADE_NOTES.items()}  # one line each
    assert CAT[CAT["formula"].notna()]["notes"].isna().all()


def test_no_placeholder_formula_tokens():
    """A token like 'unspecified' would parse to an empty element-count dict and look like a plausible zero downstream."""
    for f in CAT["formula"].dropna():
        assert re.search(r"[A-Z][a-z]?\d*", f) and not re.search(r"unspec|unknown|n/a|tbd|none", f, re.I), f


def test_density_is_null_for_every_polymer_and_every_one_is_logged_as_a_density_gap():
    assert CAT["density_g_cm3"].isna().all() and CAT["density_source"].isna().all()
    dens = GAPS[GAPS["gap_kind"] == "density"]
    assert len(dens) == 41 and dens["reason"].str.contains("no traceable density source").all()
    assert set(CAT["abbreviation"]) == set(dens["key"])


# ---- scope decisions -------------------------------------------------------------------------------------------

def test_nothing_is_deferred_any_more_the_five_were_resolved_per_the_accepted_defaults():
    assert pml.DEFERRED == {} and not [k for k, v in SEL.items() if v.get("deferred")]
    assert not GAPS[GAPS["gap_kind"] == "deferred"].shape[0]
    for k in ("PS", "PVA", "Kapton", "PMMA-Tomson", "PMMA-Mitsubishi", "PDMS-5-1", "PDMS-10-1", "PDMS-15-1", "PDMS-20-1"):
        assert k in set(CAT["abbreviation"]) and "axes" in SEL[k]
    assert "PMMA" not in SEL and "PDMS" not in SEL, "the parent PMMA/PDMS were replaced by per-supplier / per-cure-ratio rows"


def test_catalog_excluded_candidates_and_gaps_partition_the_92_candidate_pool_without_overlap():
    whole = set(GAPS[GAPS["gap_kind"] == "material"]["key"])
    cat = set(CAT["abbreviation"])
    excluded_cands = set(pml.EXCLUDED_CANDIDATES)
    assert len(cat) + len(excluded_cands) + len(whole) == 94 == len(pml.CANDIDATES)
    assert not cat & whole and not cat & excluded_cands and not excluded_cands & whole
    assert cat | excluded_cands | whole == {c["key"] for c in pml.CANDIDATES}


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


def test_identity_flags_pei_collision_pla_is_pdla_ldpe_is_a_gap_and_lldpe_is_its_own_row():
    pei = CAT[CAT["abbreviation"] == "PEI"].iloc[0]
    assert pei["name"] == "Polyetherimide (PEI)" and "NAME COLLISION" in pei["flags"] and "polyethylenimine" in pei["flags"]
    pla = CAT[CAT["abbreviation"] == "PLA"].iloc[0]
    assert "PDLA" in pla["name"] and "PDLA" in pla["flags"]
    assert GAPS[GAPS["key"] == "PE-LDPE"].iloc[0]["gap_kind"] == "material" and "PE-LDPE" not in set(CAT["abbreviation"])
    owners = [k for k, v in SEL.items() if "axes" in v and any("David" in json.dumps(a) for a in v["axes"])]
    assert owners == ["PE-LLDPE"], "the LLDPE page is loaded only as its own LLDPE row, never as LDPE"


def test_no_selected_dataset_is_ambiguous_or_shared_between_materials():
    paths = [a["data_path"] for _, a in SELECTED]
    assert len(paths) == len(set(paths)) == 50  # 41 materials: 34 single-dataset + 6 conjugated polymers with two axes each + the 950 PMMA resist's 4
    assert all(a["dataset_label"] for _, a in SELECTED)
    for k, v in SEL.items():
        labels = [a["dataset_label"] for a in v["axes"]]
        assert len(labels) == len(set(labels)), f"{k}: dataset labels must be distinct within a material"
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


# ---- batch 2 decisions -----------------------------------------------------------------------------------------

def _hand_n(path, lam_um=0.633):
    """n(633 nm) evaluated directly from the YAML (Sellmeier 1/2, polynomial 3, Cauchy 5, or the tabulated rows) -- independent of parse_file."""
    for b in yaml.safe_load(open(RI / path))["DATA"]:
        t = b["type"]
        if t.startswith("formula"):
            lo, hi = [float(x) for x in b["wavelength_range"].split()]
            if not lo <= lam_um <= hi:
                continue
            c, l2 = [float(x) for x in b["coefficients"].split()], lam_um ** 2
            if t == "formula 1":
                return (1 + c[0] + sum(c[i] * l2 / (l2 - c[i + 1] ** 2) for i in range(1, len(c) - 1, 2))) ** 0.5
            if t == "formula 2":
                return (1 + c[0] + sum(c[i] * l2 / (l2 - c[i + 1]) for i in range(1, len(c) - 1, 2))) ** 0.5
            if t == "formula 3":  # polynomial: n^2 = c0 + sum c_i * lambda^c_{i+1}
                return (c[0] + sum(c[i] * lam_um ** c[i + 1] for i in range(1, len(c) - 1, 2))) ** 0.5
            if t == "formula 5":
                return c[0] + sum(c[i] * lam_um ** c[i + 1] for i in range(1, len(c) - 1, 2))
            raise AssertionError(f"unsupported formula type {t}")
        rows = [[float(x) for x in ln.split()] for ln in b["data"].strip().splitlines()]
        if rows[0][0] <= lam_um <= rows[-1][0]:
            return float(np.interp(lam_um, [r[0] for r in rows], [r[1] for r in rows]))
    return None


def _n633(monkeypatch, shelf_book_page):
    """n(633 nm) for a catalog page, from parse_file (the loader's own path), asserted equal to the hand evaluation."""
    monkeypatch.setattr(fod, "WL_MIN_NM", 0.01)
    monkeypatch.setattr(fod, "WL_MAX_NM", 2_000_000.0)
    path = next(d["data_path"] for c in MATCHES.values() for d in c["datasets"] if (d["shelf"], d["book"], d["page"]) == shelf_book_page) \
        if any((d["shelf"], d["book"], d["page"]) == shelf_book_page for c in MATCHES.values() for d in c["datasets"]) else None
    if path is None:  # excluded pages are not in the candidate's dataset list: look the file up in the RI catalog
        cat = yaml.safe_load(open(ROOT / "refractiveindex_db" / "database" / "catalog-nk.yml"))
        path = next(p["data"] for e in cat if e.get("SHELF") == shelf_book_page[0] for b in e.get("content", []) if b.get("BOOK") == shelf_book_page[1]
                    for p in b.get("content", []) if p.get("PAGE") == shelf_book_page[2])
    wl, n, *_ = fod.parse_file(RI / path)
    via_parse = float(np.interp(633.0, wl, n)) if wl.min() <= 633 <= wl.max() else None
    hand = _hand_n(path)
    assert (via_parse is None) == (hand is None) and (via_parse is None or via_parse == pytest.approx(hand, abs=1e-4)), (path, via_parse, hand)
    return via_parse


def test_ps_zhang_only_and_the_sultanova_disagreement_is_re_derived_from_source(monkeypatch):
    assert [a["page"] for a in SEL["PS"]["axes"]] == ["Zhang"]
    ex = {r["key"]: r["reason"] for _, r in GAPS[GAPS["gap_kind"] == "excluded_dataset"].iterrows()}
    assert set(k for k in ex if k.startswith("PS:")) == {"PS:Sultanova", "PS:Juntunen", "PS:Nyakuchena", "PS:Myers"}
    z, sul = _n633(monkeypatch, (ORG_, "polystyrene", "Zhang")), _n633(monkeypatch, (ORG_, "polystyrene", "Sultanova"))
    assert round(abs(sul - z) / z * 100, 1) == 0.1 and "~0.1%" in ex["PS:Sultanova"]
    assert "packing artifact" in ex["PS:Juntunen"] and "microspheres" in ex["PS:Nyakuchena"]


ORG_ = "organic"


def test_pmma_is_one_row_per_supplier_and_every_stated_percent_is_re_derived_from_source(monkeypatch):
    assert [a["page"] for a in SEL["PMMA-Tomson"]["axes"]] == ["Zhang-Tomson"] and [a["page"] for a in SEL["PMMA-Mitsubishi"]["axes"]] == ["Zhang-Mitsubishi"]
    tom, mit = (_n633(monkeypatch, (ORG_, "poly_methyl_methacrylate", p)) for p in ("Zhang-Tomson", "Zhang-Mitsubishi"))
    assert (tom - mit) / mit * 100 == pytest.approx(-0.52, abs=0.01)  # the measured reason the suppliers are separate materials
    for shelf, book, page, reason in pml.PMMA_EXCLUDED:
        m = re.search(r"([+-]\d+\.\d+)% \(Tomson\) / ([+-]\d+\.\d+)% \(Mitsubishi\)", reason)
        if not m:
            continue
        n = _n633(monkeypatch, (shelf, book, page))
        assert (n - tom) / tom * 100 == pytest.approx(float(m.group(1)), abs=0.01) and (n - mit) / mit * 100 == pytest.approx(float(m.group(2)), abs=0.01), page
    keys = {k for k in GAPS[GAPS["gap_kind"] == "excluded_dataset"]["key"] if k.startswith("PMMA-Tomson:")}
    assert len(keys) == 5 == len(pml.PMMA_EXCLUDED) and len(set(keys)) == 5  # the 5 resist pages moved to PMMA-495/950-resist


def test_pdms_is_one_row_per_cure_ratio_and_the_ratio_is_stated_by_each_source_file():
    for ratio in ("5-1", "10-1", "15-1", "20-1"):
        (ax,) = SEL[f"PDMS-{ratio}"]["axes"]
        comment = yaml.safe_load(open(RI / ax["data_path"]))["COMMENTS"]
        assert f"= {ratio.replace('-', ':')}" in comment and "Dow Corning" in comment, (ratio, comment)
    reasons = {r["key"]: r["reason"] for _, r in GAPS[GAPS["gap_kind"] == "excluded_dataset"].iterrows() if r["key"].startswith("PDMS-5-1:")}
    assert len(reasons) == 6 and any("different chemistry" in v for v in reasons.values()) and sum("FLUID" in v for v in reasons.values()) == 2


def test_pva_schnepf_only_and_kapton_hn_french_only_with_every_other_page_logged():
    assert [a["page"] for a in SEL["PVA"]["axes"]] == ["Schnepf"]
    assert [a["page"] for a in SEL["Kapton"]["axes"]] == ["French"] and "Kapton HN" in yaml.safe_load(open(RI / SEL["Kapton"]["axes"][0]["data_path"]))["COMMENTS"]
    kap = GAPS[GAPS["key"].str.startswith("Kapton:")]
    assert len(kap) == 9 and set(kap["gap_kind"]) == {"excluded_dataset"}  # 7 other n,k pages + 2 k-only pages
    assert sum("k-only" in r for r in kap["reason"]) == 2


def test_conjugated_polymers_load_both_axes_of_one_paper_with_distinct_labels():
    for k in ("MDMO-PPV", "ZZ50", "F8BT", "PTB7", "PDCBT", "PBDB-T-2F"):
        axes = SEL[k]["axes"]
        assert [a["dataset_label"] for a in axes] == ["Kamptner2024 | o-ray", "Kamptner2024 | e-ray"] and [a["page"] for a in axes] == ["Kamptner-o", "Kamptner-e"]
        assert CAT[CAT.abbreviation == k].iloc[0]["n_selected_datasets"] == 2 and CAT[CAT.abbreviation == k].iloc[0]["materialclass"] == "organic_semiconductor"


def test_resists_ip_cured_only_hpmc_powder_excluded_and_the_mixture_is_blocked():
    for k in ("IP-S", "IP-Dip"):
        (ax,) = SEL[k]["axes"]
        assert ax["page"] == "Mavrona-cured" and "Cured" in yaml.safe_load(open(RI / ax["data_path"]))["COMMENTS"]
        ex = GAPS[GAPS["key"].str.startswith(f"{k}:")].iloc[0]
        assert ex["gap_kind"] == "excluded_dataset" and "Uncured" in ex["reason"]
    assert "HPMC" not in set(CAT["abbreviation"]) and "Powder" in yaml.safe_load(open(RI / MATCHES["HPMC"]["datasets"][0]["data_path"]))["COMMENTS"]
    assert GAPS[GAPS["key"] == "HPMC"].iloc[0]["gap_kind"] == "excluded_dataset"
    assert GAPS[GAPS["key"] == "maN-405-T1050"].iloc[0]["tier"] == "BLOCKED" and "maN-405-T1050" not in set(CAT["abbreviation"])


def test_pmma_resists_are_their_own_materials_with_the_uncured_and_mixture_decisions_intact():
    """The MicroChem PMMA resists are loaded as photoresists, never as bulk PMMA; the earlier decisions stand: uncured resists
    (SU-8 2000, IP-S / IP-Dip uncured) are not material constants and the ma-N 405 : ma-T 1050 mixture stays blocked."""
    from dataset_kind import is_model_fit
    r950 = SEL["PMMA-950-resist"]["axes"]
    assert [a["dataset_label"] for a in r950][0] == "Microchem-datasheet-2001" and not is_model_fit(r950[0]["data_path"])
    assert {a["page"] for a in r950} == {"specs", "Tsuda", "Tsuda-LD", "Tsuda-BB"}
    assert [is_model_fit(a["data_path"]) for a in r950] == [False, False, True, True]  # the LD / BB pages are model fits
    assert [a["page"] for a in SEL["PMMA-495-resist"]["axes"]] == ["specs"]
    for key in ("PMMA-Tomson", "PMMA-Mitsubishi"):
        assert not {a["data_path"] for a in SEL[key]["axes"]} & {a["data_path"] for a in r950}
    loaded = {a["data_path"] for v in SEL.values() if v and v.get("axes") for a in v["axes"]}
    assert not [p for p in loaded if "SU-8 2000" in p or "uncured" in p.lower() or "ma-N 405" in p or "ma-N405" in p]
    assert "maN-405-T1050" not in SEL or SEL["maN-405-T1050"] is None
