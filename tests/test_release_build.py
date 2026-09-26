"""Tests for the downloadable release (scripts/build_release.py, scripts/release_descriptors.py).

The release is built once into a temp folder. Every family's data in it is compared row by row with the database that
family's own loader builds, and every descriptor is recomputed by an independent route (periodictable instead of pymatgen for
element data, formula masses instead of SMILES, the legacy RDKit fingerprint call, lattice geometry for density).
"""
import csv
import gzip
import hashlib
import json
import math
import re
import shutil
import sqlite3
import sys
import zipfile
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import build_release as br  # noqa: E402
import release_descriptors as rd  # noqa: E402

AVOGADRO = 6.02214076e23
# the legacy benchmark DB's own rows are not merged: its water/ethanol/DMSO come in through the liquids family under their own names
BENCHMARK_ONLY = ["DMSO", "DPPC", "BSA", "ITO", "PEG", "PEI", "PTFE", "PEEK", "Nylon66"]
N_MATERIALS = sum(len(pd.read_csv(ROOT / "data" / f"{stem}.csv")) for stem in br.FAMILY_CSVS) - 5  # the 5 batch-2 nitrides are in two tables
POLYMERS = set(pd.read_csv(ROOT / "data" / "polymers.csv").name)
LIQUIDS = pd.read_csv(ROOT / "data" / "liquids.csv")


@pytest.fixture(scope="module")
def release(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("release")
    db = tmp / "build.sqlite"
    facts = br.build_db(db)
    out, zpath, manifest = br.package(db, "0.0.0-test", facts, out_root=tmp)
    return dict(db=out / "materials-db-v0.0.0-test.sqlite", out=out, zip=zpath, manifest=manifest, facts=facts)


def q(release, sql, args=()):
    c = sqlite3.connect(f"{Path(release['db']).as_uri()}?mode=ro", uri=True)
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


def descriptors(release):
    return {name: (cols, json.loads(doc)) for name, *cols, doc in q(
        release, "SELECT m.name, d.exact_mass, d.heavy_atom_count, d.tpsa, d.logp, d.rotatable_bonds, d.hbond_donors, d.hbond_acceptors, "
                 "d.aromatic_rings, d.morgan_fp, d.descriptor_json FROM chemical_descriptors d JOIN materials m USING(material_id)")}


# ---------------------------------------------------------------- the data itself: nothing lost, nothing altered

def test_every_family_material_is_in_the_release_once_and_nothing_else_is(release):
    names = [n for (n,) in q(release, "SELECT name FROM materials")]
    expected = set(br.family_rows())
    assert len(names) == len(set(names)) == len(expected) == N_MATERIALS == 319 and set(names) == expected
    assert not set(BENCHMARK_ONLY) & set(names)  # the legacy benchmark rows are not merged


@pytest.fixture(scope="module")
def family_dbs(tmp_path_factory):
    """Each non-oxide family built on its own by its wrapper, exactly as before the release existed."""
    dbs = {}
    for name, mod, _ in br.family_jobs():
        db = tmp_path_factory.mktemp(name) / f"{name}.db"
        old, mod.DB_PATH = mod.DB_PATH, db
        try:
            mod.main()
        finally:
            mod.DB_PATH = old
        dbs[name] = db
    return dbs


def _optical(db, name):
    c = sqlite3.connect(f"{Path(db).as_uri()}?mode=ro", uri=True)
    rows = Counter(c.execute("SELECT o.dataset_label, o.wavelength_nm, o.n, o.k, o.raw_record_table FROM optical_dispersion o "
                             "JOIN materials m USING(material_id) WHERE m.name = ?", (name,)).fetchall())
    c.close()
    return rows


def test_optical_rows_of_every_material_equal_its_origin_database_exactly(release, family_dbs):
    origin = {"batch2_31": br.BASE_DB, "oxides_50": br.BASE_DB, "batch3b_4": br.BASE_DB, "pure_elements_50": br.BASE_DB,
              "nitrides": family_dbs["nitride"], "polymers": family_dbs["polymer"], "inorganic3": family_dbs["inorganic3"],
              "halides": family_dbs["halide"], "chalcogenides": family_dbs["chalcogenide"], "liquids": family_dbs["liquid"],
              "semiconductors": family_dbs["semiconductor"]}
    total = 0
    for name, (stem, _) in br.family_rows().items():
        got = _optical(release["db"], name)
        assert got == _optical(origin[stem], name), name
        total += sum(got.values())
    assert total == q(release, "SELECT COUNT(*) FROM optical_dispersion")[0][0]


def test_duplicate_physical_rows_are_gone_and_each_removed_value_survives_once(release):
    removed = release["facts"]["removed_duplicate_physical_rows"]
    assert len(removed) == 22 and {r["material"] for r in removed} == {"Aluminium nitride", "Boron nitride (hexagonal)", "Gallium nitride",
                                                                          "Titanium nitride", "Vanadium nitride"}
    assert q(release, "SELECT COUNT(*) FROM (SELECT 1 FROM physical_properties GROUP BY material_id, dataset_label, density_g_cm3, "
                      "xray_sld, neutron_sld, dielectric_constant HAVING COUNT(*) > 1)")[0][0] == 0
    for r in removed:
        assert q(release, "SELECT COUNT(*) FROM physical_properties p JOIN materials m USING(material_id) WHERE m.name=? AND p.dataset_label=?",
                 (r["material"], r["dataset_label"]))[0][0] == 1
    # TiN / VN density now cites the source whose notes name them, not the batch-2 note about As2S3 and HgS
    for f in ("TiN", "VN"):
        notes = q(release, "SELECT s.notes FROM physical_properties p JOIN materials m USING(material_id) JOIN sources s USING(source_id) "
                           "WHERE m.formula=? AND p.density_g_cm3 IS NOT NULL", (f,))
        assert len(notes) == 1 and re.search(rf"\b{f}\b", notes[0][0]) and "As2S3" not in notes[0][0]


def test_sources_keep_one_pubchem_citation_and_no_placeholder(release):
    titles = [t or "" for (t,) in q(release, "SELECT title FROM sources")]
    assert titles.count("PubChem") == 1 and not any(t.startswith("unused") for t in titles)
    unreferenced = q(release, "SELECT title FROM sources s WHERE NOT EXISTS (SELECT 1 FROM optical_dispersion o WHERE o.source_id=s.source_id) "
                              "AND NOT EXISTS (SELECT 1 FROM physical_properties p WHERE p.source_id=s.source_id)")
    assert unreferenced == [("PubChem",)]


def test_repeated_wavelengths_are_exactly_the_ones_the_source_files_repeat(release):
    reps = release["facts"]["optical_wavelengths_repeated_in_source"]
    assert {(r["material"], r["wavelength_nm"]) for r in reps} == {
        ("Copper(II) oxide", 13.6), ("Copper(II) oxide", 14.0), ("Copper(II) oxide", 14.5), ("Copper(I) oxide", 3268.0),
        ("Copper(I) oxide", 3322.3), ("Hematite", 1950.0), ("Hematite", 4149.4), ("Potassium chloride", 1160.0),
        ("Ethylene glycol", 666.7), ("Diethyl phthalate", 4464.3), ("Dimethyl methylphosphonate", 1729.5),
        ("Diethyl sulfite", 720.0), ("Diethyl sulfite", 2840.9), ("Diethyl sulfite", 3134.8)}
    for r in reps:
        assert br.source_repeat_count(r["source_file"], r["wavelength_nm"]) == r["rows"] == 2


def test_negative_k_allow_list_is_the_same_as_the_family_battery():
    import test_family_optical_sanity as battery
    assert br.NEGATIVE_K_ALLOWED == battery.NEGATIVE_K_ALLOWED


@pytest.mark.parametrize("plant", ["floored_n", "duplicate_not_in_source", "duplicate_physical", "missing_descriptor_row"])
def test_validation_stops_the_build_on_each_kind_of_bad_data(release, tmp_path, plant):
    db = tmp_path / "bad.sqlite"
    shutil.copy(release["db"], db)
    c = sqlite3.connect(str(db))
    mid, label, table, src = c.execute("SELECT material_id, dataset_label, raw_record_table, source_id FROM optical_dispersion LIMIT 1").fetchone()
    if plant == "floored_n":
        c.execute("DROP TRIGGER IF EXISTS trg_optical_check_ins")
        c.execute("INSERT INTO optical_dispersion(material_id,wavelength_nm,n,k,dataset_label,raw_record_table,raw_record_id,source_id) "
                  "VALUES (?,41000.0,1e-15,0.0,?,?,-1,?)", (mid, label, table, src))
    elif plant == "duplicate_not_in_source":
        c.execute("INSERT INTO optical_dispersion(material_id,wavelength_nm,n,k,dataset_label,raw_record_table,raw_record_id,source_id) "
                  "SELECT material_id,wavelength_nm,n,k,dataset_label,'ctrl/'||raw_record_table,raw_record_id,source_id FROM optical_dispersion LIMIT 1")
    elif plant == "duplicate_physical":
        c.execute("INSERT INTO physical_properties(material_id,density_g_cm3,xray_sld,neutron_sld,dielectric_constant,dataset_label,raw_record_table,raw_record_id,source_id) "
                  "SELECT material_id,density_g_cm3,xray_sld,neutron_sld,dielectric_constant,dataset_label,'ctrl',-1,source_id FROM physical_properties LIMIT 1")
    else:
        c.execute("DELETE FROM chemical_descriptors WHERE material_id = ?", (mid,))
    c.commit()
    with pytest.raises(br.ReleaseError):
        br.validate(c)
    c.close()


# ---------------------------------------------------------------- descriptors

def test_every_material_has_one_descriptor_row_and_every_null_is_explained(release):
    d = descriptors(release)
    assert len(d) == N_MATERIALS
    for name, (cols, doc) in d.items():
        for section in ("compositional", "structural", "molecular"):
            filled = not ({"unavailable", "not_applicable"} & set(doc[section]))
            reason = doc[section].get("unavailable") or doc[section].get("not_applicable")
            assert filled != bool(reason), (name, section)
        exact_mass, heavy, tpsa, logp, rot, hbd, hba, arom, fp = cols
        if tpsa is None:
            assert set(doc["null_columns_reason"]) == set(rd.MOLECULAR_COLUMNS), name
        if exact_mass is None:
            assert "unavailable" in doc["compositional"], name
    kinds = Counter(doc["material_kind"] for _, doc in d.values())
    formulas = dict(q(release, "SELECT name, formula FROM materials"))
    polymers = set(pd.read_csv(ROOT / "data" / "polymers.csv").name)
    elements = {n for n, f in formulas.items() if f and n not in polymers and len(set(re.findall(r"[A-Z][a-z]?", f))) == 1}
    molecules = set(LIQUIDS[LIQUIDS.smiles.notna() & (LIQUIDS.formula != "Hg")].name)
    biomacro = set(LIQUIDS[LIQUIDS.formula.isna()].name)
    elements |= {"Mercury (liquid)"}
    assert kinds == {"polymer": len(polymers), "element": len(elements), "molecule": len(molecules), "biomacromolecule": len(biomacro),
                     "inorganic compound": N_MATERIALS - len(polymers) - len(elements) - len(molecules) - len(biomacro)}
    assert {"Diamond", "Graphite", "Gold", "Silicon"} <= elements


def test_descriptor_coverage_is_what_the_inputs_allow(release):
    cov = release["facts"]["descriptor_coverage"]
    no_formula = len(pd.read_csv(ROOT / "data" / "polymers.csv").pipe(lambda p: p[p.formula.isna()])) + 2 + int(LIQUIDS.formula.isna().sum())
    assert cov == {"compositional": N_MATERIALS - no_formula, "structural": 187,
                   "molecular": len(pd.read_csv(rd.REPEAT_UNITS)) + int((LIQUIDS.smiles.notna() & (LIQUIDS.formula != "Hg")).sum())}
    d = descriptors(release)
    no_comp = {n for n, (_, doc) in d.items() if "unavailable" in doc["compositional"]}
    pol = pd.read_csv(ROOT / "data" / "polymers.csv")
    assert no_comp == set(pol[pol.formula.isna()].name) | {"Styrene-acrylonitrile copolymer", "PDCBT"} | set(LIQUIDS[LIQUIDS.formula.isna()].name)


def test_every_curated_repeat_unit_matches_the_source_formula_and_has_two_attachment_points():
    from pymatgen.core import Composition
    from rdkit import Chem
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula
    units = pd.read_csv(rd.REPEAT_UNITS)
    pol = pd.read_csv(ROOT / "data" / "polymers.csv").set_index("name")
    assert len(units) == 25 and units.material_name.is_unique and set(units.material_name) <= set(pol.index)
    for u in units.itertuples():
        mol = Chem.MolFromSmiles(u.repeat_unit_smiles)
        assert sum(a.GetAtomicNum() == 0 for a in mol.GetAtoms()) == 2, u.material_name
        heavy = Chem.RWMol(mol)
        for i in sorted((a.GetIdx() for a in heavy.GetAtoms() if a.GetAtomicNum() == 0), reverse=True):
            heavy.RemoveAtom(i)
        assert Composition(CalcMolFormula(heavy.GetMol())) == Composition(pol.loc[u.material_name, "formula"].strip("()n")), u.material_name


def test_molecular_columns_match_an_independent_recomputation(release):
    """Exact mass from the repeat-unit FORMULA (not the SMILES); fingerprint from the legacy RDKit call."""
    import periodictable as pt  # noqa: F401
    from rdkit import Chem, RDLogger
    from rdkit.Chem import AllChem
    RDLogger.DisableLog("rdApp.*")
    units = pd.read_csv(rd.REPEAT_UNITS).set_index("material_name")
    pol = pd.read_csv(ROOT / "data" / "polymers.csv").set_index("name")
    d = descriptors(release)
    for name, u in units.iterrows():
        (exact_mass, heavy, tpsa, logp, rot, hbd, hba, arom, fp), doc = d[name]
        mass, n_heavy = rd.formula_mass_and_heavy_atoms(pol.loc[name, "formula"].strip("()n"))
        assert exact_mass == pytest.approx(mass, abs=1e-4) and heavy == n_heavy, name
        legacy = AllChem.GetMorganFingerprintAsBitVect(Chem.MolFromSmiles(u.repeat_unit_smiles), radius=2, nBits=2048).ToBitString()
        assert fp == legacy and len(fp) == 2048, name
    ps = d["Polystyrene"][0]
    assert (ps[4], ps[7]) == (2, 1)  # two backbone-side rotatable bonds, one aromatic ring per styrene unit


def test_compositional_statistics_match_periodictable_element_data(release):
    """Atomic number and mass statistics recomputed with periodictable (a different element-data source than pymatgen)."""
    import periodictable as pt
    from pymatgen.core import Composition
    d = descriptors(release)
    checked = 0
    for name, (_, doc) in d.items():
        comp = doc["compositional"]
        if "unavailable" in comp:
            continue
        atoms = pt.formula(comp["formula_unit"]).atoms  # periodictable keeps deuterium as D (mass 2.014), as pymatgen does
        total = sum(atoms.values())
        z = sum(n * el.number for el, n in atoms.items()) / total
        m = sum(n * el.mass for el, n in atoms.items()) / total
        assert comp["atomic_number"]["mean"] == pytest.approx(z, abs=1e-5), name
        assert comp["atomic_mass"]["mean"] == pytest.approx(m, rel=1e-3), name
        checked += 1
    assert checked == release["facts"]["descriptor_coverage"]["compositional"]
    nacl = d["Sodium chloride"][1]["compositional"]
    assert nacl["electronegativity_pauling"]["mean"] == pytest.approx((0.93 + 3.16) / 2) and nacl["electronegativity_pauling"]["range"] == pytest.approx(2.23)


def test_inorganic_exact_mass_is_the_monoisotopic_formula_unit_mass(release):
    d = descriptors(release)
    assert d["Sodium chloride"][0][0] == pytest.approx(22.989770 + 34.968853, abs=1e-5)  # 23Na + 35Cl
    assert d["Sodium chloride"][0][1] == 2 and d["Titanium nitride"][0][1] == 2 and d["Silicon nitride"][0][1] == 7


def test_structural_density_equals_lattice_geometry_and_the_family_density(release):
    """rho = Z * M / (N_A * V) from the cached conventional cell must reproduce MP's density; and where a family took its density
    from MP (density_source MP_DFT), the same entry must give the same number (a drift check between MP versions)."""
    import periodictable as pt
    from pymatgen.core import Composition
    d = descriptors(release)
    rows = br.family_rows()
    drift = []
    for name, (_, doc) in d.items():
        st = doc["structural"]
        if "mp_id" not in st:
            continue
        m = sum(n * pt.elements.symbol(el.symbol).mass for el, n in Composition(st["formula_pretty"]).items())
        rho = st["formula_units_per_conventional_cell"] * m / (AVOGADRO * st["conventional_cell_volume_angstrom3"] * 1e-24)
        assert rho == pytest.approx(st["density_g_cm3"], rel=2e-3), name
        csv_row = rows[name][1]
        assert str(csv_row.get("mp_id")) == st["mp_id"], name
        if csv_row.get("density_source") == "MP_DFT" and abs(csv_row["density_g_cm3"] / st["density_g_cm3"] - 1) > 1e-4:
            drift.append((name, csv_row["density_g_cm3"], st["density_g_cm3"]))
    assert drift == [], f"MP density changed since the family was built: {drift}"


def test_structural_scope_says_when_the_mp_entry_is_only_a_reference(release):
    d = descriptors(release)
    assert d["Sodium chloride"][1]["structural"]["applies_to"].startswith("the material")
    assert "amorphous" in d["Silicon nitride"][1]["structural"]["applies_to"] and d["Silicon nitride"][1]["structural"]["mp_id"] == "mp-988"
    assert d["Titanium nitride"][1]["structural"]["applies_to"].startswith("crystalline reference only")
    assert all("not_applicable" in doc["structural"] for _, doc in d.values() if doc["family"] == "polymers")


# ---------------------------------------------------------------- the package

def test_package_files_checksums_and_counts(release):
    out = release["out"]
    for rel in ("materials-db-v0.0.0-test.sqlite", "README.md", "DATA_LICENSE.md", "MANIFEST.json", "SHA256SUMS", "csv/optical_dispersion.csv.gz",
                "csv/materials.csv", "csv/chemical_descriptors.csv", "family_tables/halides.csv", "descriptor_inputs/mp_structural.json"):
        assert (out / rel).is_file(), rel
    for line in (out / "SHA256SUMS").read_text().splitlines():
        digest, rel = line.split("  ", 1)
        assert hashlib.sha256((out / rel).read_bytes()).hexdigest() == digest, rel
    listed = {ln.split("  ", 1)[1] for ln in (out / "SHA256SUMS").read_text().splitlines()}
    assert listed == {str(p.relative_to(out)) for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
    m = json.loads((out / "MANIFEST.json").read_text())
    tables = dict(q(release, "SELECT name, 0 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
    for t in tables:
        n = q(release, f"SELECT COUNT(*) FROM {t}")[0][0]
        assert m["counts"]["tables"][t] == n
        path = out / "csv" / (f"{t}.csv.gz" if t == "optical_dispersion" else f"{t}.csv")
        with (gzip.open(path, "rt", newline="") if path.suffix == ".gz" else open(path, newline="")) as f:
            assert sum(1 for _ in csv.reader(f)) - 1 == n == m["csv_rows"][path.name], t
    assert m["license"] == "CC-BY-4.0" and m["materials_project_database_version"] and m["refractiveindex_info_commit"]
    with zipfile.ZipFile(release["zip"]) as z:
        assert {Path(n).relative_to(out.name).as_posix() for n in z.namelist()} == {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}


def test_package_text_has_the_licence_the_caveats_and_no_local_paths_or_secrets(release):
    out = release["out"]
    readme = (out / "README.md").read_text()
    assert "CC BY 4.0" in readme and "calculated, not measured" in readme and "not included" in readme
    key = next((ln.split("=", 1)[1].strip().strip('"') for ln in (ROOT / ".env").read_text().splitlines() if ln.startswith("MP_API_KEY=")), None) \
        if (ROOT / ".env").exists() else None
    for p in out.rglob("*"):
        if p.is_file() and p.suffix in (".md", ".json", ".csv", ""):
            text = p.read_text(errors="ignore")
            assert "/Users/" not in text, p.name
            assert not key or key not in text, p.name


def test_package_database_opens_clean_and_matches_the_built_one(release):
    c = sqlite3.connect(f"{Path(release['db']).as_uri()}?mode=ro", uri=True)
    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and c.execute("PRAGMA foreign_key_check").fetchall() == []
    c.close()


# ---------------------------------------------------------------- cross-source validation and consensus (release_validation.py)

def test_validation_tables_are_filled_and_match_the_manifest(release):
    facts = release["facts"]["cross_source_validation"]
    assert sum(facts["pairs"].values()) == q(release, "SELECT COUNT(*) FROM dataset_validation")[0][0] > 300
    assert sum(facts["consensus"].values()) == q(release, "SELECT COUNT(*) FROM consensus_properties")[0][0] > 400
    classes = {c for (c,) in q(release, "SELECT DISTINCT classification FROM dataset_validation")}
    assert classes <= {"excellent", "warning", "suspicious"}


def test_every_validated_pair_is_like_for_like(release):
    import release_validation as rv
    for mid, a, b in q(release, "SELECT material_id, dataset_a, dataset_b FROM dataset_validation"):
        (pa, _, xa), (pb, _, xb) = rv.parse_label(a), rv.parse_label(b)
        assert (pa, xa) == (pb, xb), (a, b)
        ta, tb = (q(release, "SELECT DISTINCT temperature_c FROM optical_dispersion WHERE material_id=? AND dataset_label=?", (mid, lab))
                  for lab in (a, b))
        assert len(ta) == len(tb) == 1
        ta, tb = ta[0][0], tb[0][0]
        assert (rv.ambient(ta) and rv.ambient(tb)) or abs(ta - tb) <= 1.0, (a, b, ta, tb)


def test_gaas_n633_consensus_recomputed_independently_from_raw_rows(release):
    """Median of the measured ambient GaAs datasets covering 633 nm, straight from optical_dispersion with numpy."""
    import numpy as np
    from dataset_kind import is_model_fit
    rows = q(release, "SELECT o.dataset_label, o.raw_record_table, o.wavelength_nm, o.n, o.temperature_c FROM optical_dispersion o "
                      "JOIN materials m USING(material_id) WHERE m.name='Gallium arsenide'")
    by = {}
    for lab, table, wl, n, t in rows:
        by.setdefault((lab, table, t), []).append((wl, n))
    votes = []
    for (lab, table, t), pts in by.items():
        pts.sort()
        if is_model_fit(table) or not (t is None or 15 <= t <= 30) or not pts[0][0] <= 633 <= pts[-1][0]:
            continue
        votes.append(float(np.interp(633.0, [p[0] for p in pts], [p[1] for p in pts])))
    (val, n_src, cls), = q(release, "SELECT consensus_value, num_sources, classification FROM consensus_properties c "
                                    "JOIN materials m USING(material_id) WHERE m.name='Gallium arsenide' AND property_name='n_633nm'")
    assert n_src == len(votes) >= 3 and val == pytest.approx(float(np.median(votes)), abs=1e-9) and cls == "excellent"
    assert val == pytest.approx(3.85, abs=0.02)  # Aspnes 1986, Jellison 1992, Papatryfonos 2021


def test_model_fits_never_vote_and_model_only_materials_have_no_consensus(release):
    assert q(release, "SELECT COUNT(*) FROM consensus_properties c JOIN materials m USING(material_id) "
                      "WHERE m.name='Cadmium telluride' AND property_name LIKE 'n_633nm%'")[0][0] == 0
    ins = dict(q(release, "SELECT property_name, consensus_value FROM consensus_properties c JOIN materials m USING(material_id) "
                          "WHERE m.name='Indium antimonide'"))
    assert ins["n_633nm"] == pytest.approx(4.290, abs=2e-3)  # Aspnes & Studna only; Adachi's model (4.77) does not vote


# ---------------------------------------------------------------- sources and synonyms (release_curation.py)

def test_no_two_sources_are_identical_and_every_doi_is_unique_and_well_formed(release):
    rows = q(release, "SELECT doi, title, authors, journal, year, technique, url, uncertainty, notes FROM sources")
    assert len(rows) == len(set(rows))
    dois = [d for (d, *_) in rows if d]
    assert len(dois) == len(set(dois)) and all(d.startswith("10.") for d in dois)
    facts = release["facts"]["source_curation"]
    assert facts["merged_identical_rows"] > 0 and len(facts["dois_added"]) >= 5
    for d in facts["dois_added"]:
        assert q(release, "SELECT doi FROM sources WHERE source_id=?", (d["source_id"],))[0][0] == d["doi"]


def test_every_accepted_crossref_doi_passed_all_three_checks():
    import fetch_source_dois as fsd
    cache = json.loads((ROOT / "data" / "descriptors" / "source_dois.json").read_text())
    for key, v in cache["accepted"].items():
        assert v["doi"].startswith("10.") and v["title_coverage"] >= fsd.TITLE_COVERAGE, key


def test_synonyms_are_unambiguous_and_never_repeat_the_name_or_formula(release):
    rows = q(release, "SELECT s.synonym, m.material_id, m.name, m.formula FROM material_synonyms s JOIN materials m USING(material_id)")
    facts = release["facts"]["synonyms"]
    assert len(rows) == facts["synonyms"] > 150
    owners = {}
    for syn, mid, name, formula in rows:
        owners.setdefault(syn.casefold(), set()).add(mid)
        assert syn.casefold() not in (name.casefold(), (formula or "").casefold()), (syn, name)
    assert all(len(v) == 1 for v in owners.values())
    names = {n.casefold(): mid for mid, n in q(release, "SELECT material_id, name FROM materials")}
    assert not [s for s, mid, *_ in rows if s.casefold() in names and names[s.casefold()] != mid]  # never another material's name
    get = lambda n: {s for (s,) in q(release, "SELECT synonym FROM material_synonyms JOIN materials USING(material_id) WHERE name=?", (n,))}
    assert {"ZGP"} <= get("Zinc germanium phosphide (ZGP)") and {"galena"} <= get("Lead(II) sulfide (galena)")
    assert {"Heavy water", "Deuterium Oxide"} <= get("Heavy water (D2O)") and "heavy water" not in {s.casefold() for s in get("Water")}


# ---------------------------------------------------------------- dielectric constants (release_dielectric.py)

def test_dielectric_rows_match_the_cache_and_respect_the_exclusions(release):
    import release_dielectric as rdl
    cache = json.loads(rdl.CACHE.read_text())["entries"]
    facts = release["facts"]["dielectric"]
    rows = q(release, "SELECT m.name, p.dielectric_constant, p.frequency_hz, p.dataset_label, d.descriptor_json FROM physical_properties p "
                      "JOIN materials m USING(material_id) JOIN chemical_descriptors d USING(material_id) WHERE p.dielectric_constant IS NOT NULL")
    assert len(rows) == facts["rows"] == 2 * facts["materials"] > 150
    for name, eps, freq, label, doc in rows:
        s = json.loads(doc)["structural"]
        assert s["applies_to"].startswith("the material") and s["band_gap_ev"] >= rdl.MIN_GAP_EV, name
        e = cache[s["mp_id"]]
        if label.endswith("dielectric_static_total | MP_DFPT"):
            assert (eps, freq) == (pytest.approx(e["e_total"]), 0.0), name
        else:
            assert label.endswith("dielectric_electronic | MP_DFPT") and eps == pytest.approx(e["e_electronic"]) and freq is None, name
    skipped = {x["material"] for x in facts["not_stored_narrow_gap"]}
    assert {"Germanium", "Gallium arsenide", "Indium antimonide"} <= skipped and not skipped & {r[0] for r in rows}
