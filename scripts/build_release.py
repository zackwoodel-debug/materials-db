#!/usr/bin/env python3
"""
scripts/build_release.py
=========================
Builds the downloadable dataset: ONE SQLite database holding every loaded family, plus a CSV of every table, the family
tables (they carry the per-material flags and evidence the frozen schema has no column for), a data card, the data license,
a manifest and checksums. Output: release/materials-db-v<version>/ and release/materials-db-v<version>.zip (gitignored;
publish them as GitHub release assets, not commits).

Stages, all reproducible from committed inputs (no API key, no network):
  1. base         copy data/materials_oxide_test.db (oxides, batch 2, batch 3b, pure elements; formula-4 remediated)
  2. families     upsert nitride, polymer, inorganic3, halide, chalcogenide, liquid and semiconductor through load_family_db.run_family with the same
                  options as their wrappers (conflicts are reported, never overwritten)
  3. dedupe       physical rows a later family re-loaded with identical values (the five nitrides batch 2 already held): keep
                  one, preferring the source whose title/notes name the material, else the older source; then drop sources
                  nothing references. Every removal is recorded in MANIFEST.json.
  3b. validation cross-source agreement (dataset_validation) and measured consensus at 633 nm (consensus_properties) for
                  like-for-like datasets: same material, phase, axis and temperature (scripts/release_validation.py)
  4. descriptors  one chemical_descriptors row per material (scripts/release_descriptors.py)
  5. validate     integrity, foreign keys, no duplicate rows, optical sanity; any failure stops the build
  6. package

The legacy benchmark DB (data/materials_normalized.db) is not included: its SLD units (1/A^2 vs 1e-6/A^2), raw-HTML dataset
labels and repeated rows do not match the curated families (see the README this script writes).
"""
import argparse
import contextlib
import csv
import gzip
import hashlib
import io
import json
import math
import re
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "src"))

import load_family_db as fam  # noqa: E402
import release_descriptors as rd  # noqa: E402
import release_validation as rv  # noqa: E402

BASE_DB = _ROOT / "data" / "materials_oxide_test.db"
FAMILY_CSVS = ["oxides_50", "batch2_31", "batch3b_4", "pure_elements_50", "nitrides", "polymers", "inorganic3", "halides",
               "chalcogenides", "liquids", "semiconductors"]
GAP_CSVS = ["nitride_gaps", "polymer_gaps", "inorganic3_gaps", "halide_gaps", "chalcogenide_gaps", "liquid_gaps", "semiconductor_gaps"]
DESCRIPTOR_INPUTS = ["mp_structural.json", "polymer_repeat_units.csv", "formula_issues.csv"]
# Same allow-list as tests/test_family_optical_sanity.py (a test keeps them equal): measurement noise around k = 0 in tabulated sources.
NEGATIVE_K_ALLOWED = {
    ("Copper(I) oxide", "cuprite | Querry1985"): -0.03,
    ("Hematite", "hematite | Querry1985 | o-ray"): -0.15,
    ("Micro resist ma-N 1407 (negative resist)", "Sarkar2019"): -0.03,
    ("Gallium phosphide", "Jellison1992"): -0.003,
}
N_MIN = 1e-3
BUILD_INPUTS = ["data", "scripts", "src", "DATA_LICENSE.md"]  # what the build reads; other files (e.g. NOTES.md) cannot change the release
RI_DATA = _ROOT / "refractiveindex_db" / "database" / "data"


class ReleaseError(RuntimeError):
    pass


def family_jobs():
    import load_chalcogenides_db as chl
    import load_halides_db as hal
    import load_inorganic3_db as i3
    import load_liquids_db as liq
    import load_nitrides_db as nit
    import load_polymers_db as pol  # noqa: F401  (kwargs below mirror its main())
    import load_semiconductors_db as sem
    lit = lambda m: dict(literature_title=m.LITERATURE_TITLE, literature_technique=m.LITERATURE_TECHNIQUE, literature_note=m.LITERATURE_NOTE)
    return [("nitride", nit, lit(nit)),
            ("polymer", pol, dict(allow_null_formula=True, reference_sources=False, collapse_block_duplicates=True)),
            ("inorganic3", i3, lit(i3)), ("halide", hal, lit(hal)), ("chalcogenide", chl, lit(chl)),
            ("liquid", liq, dict(lit(liq), allow_null_formula=True)), ("semiconductor", sem, lit(sem))]


def family_rows():
    """material name -> (family CSV stem, CSV row as dict). A name in two CSVs (the five nitrides of batch 2) must agree on mp_id."""
    out = {}
    for stem in FAMILY_CSVS:
        for row in pd.read_csv(_ROOT / "data" / f"{stem}.csv").to_dict("records"):
            name = row["name"]
            if name in out:
                a, b = out[name][1].get("mp_id"), row.get("mp_id")
                if str(a) != str(b):
                    raise ReleaseError(f"{name!r} is in {out[name][0]} and {stem} with different mp_id ({a} vs {b})")
                continue
            out[name] = (stem, row)
    return out


def _v(x):
    return None if x is None else float(f"{x:.12g}")


def dedupe_physical(conn):
    rows = conn.execute(
        "SELECT p.record_id, p.material_id, m.name, m.formula, p.dataset_label, p.density_g_cm3, p.xray_sld, p.neutron_sld, "
        "p.dielectric_constant, p.source_id, COALESCE(s.title,'') || ' ' || COALESCE(s.notes,'') "
        "FROM physical_properties p JOIN materials m USING(material_id) JOIN sources s USING(source_id)").fetchall()
    groups = defaultdict(list)
    for r in rows:
        groups[(r[1], r[4], _v(r[5]), _v(r[6]), _v(r[7]), _v(r[8]))].append(r)
    removed = []
    for rs in groups.values():
        if len(rs) < 2:
            continue
        formula = rs[0][3] or ""
        naming = [r for r in rs if formula and re.search(rf"(?<![A-Za-z0-9]){re.escape(formula)}(?![a-z0-9])", r[10])]
        keep = min(naming or rs, key=lambda r: r[9])
        for r in rs:
            if r is not keep:
                conn.execute("DELETE FROM physical_properties WHERE record_id = ?", (r[0],))
                removed.append(dict(material=r[2], dataset_label=r[4], removed_source_id=r[9], kept_source_id=keep[9],
                                    kept_because="its source names the material" if naming else "older source"))
    orphans = conn.execute(
        "SELECT source_id, title FROM sources s WHERE NOT EXISTS (SELECT 1 FROM optical_dispersion o WHERE o.source_id = s.source_id) "
        "AND NOT EXISTS (SELECT 1 FROM physical_properties p WHERE p.source_id = s.source_id) "
        "AND NOT EXISTS (SELECT 1 FROM mechanical_properties x WHERE x.source_id = s.source_id) "
        "AND NOT EXISTS (SELECT 1 FROM rheology r WHERE r.source_id = s.source_id)").fetchall()
    # PubChem is cited for the identifiers in `materials`, which has no source column, so its row is never referenced by a key:
    # keep one (the oldest) as the citation and drop the per-batch copies. Every other unreferenced source is a leftover.
    keep_pubchem = min((sid for sid, t in orphans if t == "PubChem"), default=None)
    dropped = [(sid, t) for sid, t in orphans if sid != keep_pubchem]
    for sid, _ in dropped:
        conn.execute("DELETE FROM sources WHERE source_id = ?", (sid,))
    return removed, [dict(source_id=s, title=t) for s, t in dropped]


def populate_descriptors(conn):
    mp, units, issues = rd.load_inputs()
    rows = family_rows()
    labels = defaultdict(list)
    for mid, lab in conn.execute("SELECT DISTINCT material_id, dataset_label FROM optical_dispersion"):
        labels[mid].append(lab)
    conn.execute("DELETE FROM chemical_descriptors")
    coverage = defaultdict(int)
    for mid, name, formula, smiles in conn.execute("SELECT material_id, name, formula, smiles FROM materials ORDER BY material_id").fetchall():
        if name not in rows:
            raise ReleaseError(f"material {name!r} is in the DB but in no family CSV")
        family, csv_row = rows[name]
        cols, doc = rd.descriptor_row(name, formula, family, csv_row, labels[mid], mp, units, issues, smiles=smiles)
        conn.execute("INSERT INTO chemical_descriptors(material_id, exact_mass, tpsa, logp, heavy_atom_count, rotatable_bonds, hbond_donors, "
                     "hbond_acceptors, aromatic_rings, descriptor_json, morgan_fp) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (mid, cols["exact_mass"], cols["tpsa"], cols["logp"], cols["heavy_atom_count"], cols["rotatable_bonds"],
                      cols["hbond_donors"], cols["hbond_acceptors"], cols["aromatic_rings"], json.dumps(doc, sort_keys=True), cols["morgan_fp"]))
        for section in ("compositional", "structural", "molecular"):
            if not ({"unavailable", "not_applicable"} & set(doc[section])):
                coverage[section] += 1
    return dict(coverage)


def validate(conn):
    problems = []
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        problems.append("integrity_check failed")
    if conn.execute("PRAGMA foreign_key_check").fetchall():
        problems.append("foreign key violations")
    n_mat = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    n_desc = conn.execute("SELECT COUNT(*) FROM chemical_descriptors").fetchone()[0]
    if n_desc != n_mat:
        problems.append(f"{n_mat} materials but {n_desc} descriptor rows")
    for name, label, wl, n, k in conn.execute("SELECT m.name, o.dataset_label, o.wavelength_nm, o.n, o.k FROM optical_dispersion o JOIN materials m USING(material_id)"):
        if n is None or not math.isfinite(n) or n <= N_MIN:
            problems.append(f"{name} | {label} | {wl} nm: n={n}")
        if wl is None or not math.isfinite(wl) or wl <= 0:
            problems.append(f"{name} | {label}: wavelength {wl}")
        if k is not None and (not math.isfinite(k) or (k < 0 and k < NEGATIVE_K_ALLOWED.get((name, label), 0.0))):
            problems.append(f"{name} | {label} | {wl} nm: k={k}")
    source_repeats = []
    for name, label, wl, count, table in conn.execute(
            "SELECT m.name, o.dataset_label, o.wavelength_nm, COUNT(*), MIN(o.raw_record_table) FROM optical_dispersion o "
            "JOIN materials m USING(material_id) GROUP BY o.material_id, o.dataset_label, o.wavelength_nm HAVING COUNT(*) > 1").fetchall():
        if source_repeat_count(table, wl) >= count:  # the refractiveindex.info file itself lists this wavelength twice: kept as published
            source_repeats.append(dict(material=name, dataset_label=label, wavelength_nm=round(wl, 6), rows=count, source_file=table))
        else:
            problems.append(f"duplicate optical rows not present in the source: {name} | {label} | {wl} nm")
    phys_dups = conn.execute("SELECT COUNT(*) FROM (SELECT 1 FROM physical_properties GROUP BY material_id, dataset_label, "
                             "density_g_cm3, xray_sld, neutron_sld, dielectric_constant HAVING COUNT(*) > 1)").fetchone()[0]
    if phys_dups:
        problems.append(f"{phys_dups} duplicated physical_properties groups")
    if problems:
        raise ReleaseError(f"{len(problems)} validation problem(s): " + "; ".join(problems[:10]))
    return source_repeats


def source_repeat_count(data_path, wavelength_nm):
    """How many times the refractiveindex.info file lists this wavelength in its tabulated blocks."""
    import yaml
    path = RI_DATA / str(data_path)
    if not path.exists():
        return 0
    n = 0
    for b in yaml.safe_load(open(path)).get("DATA", []):
        if b.get("type", "").startswith("tabulated"):
            n += sum(1 for ln in b["data"].strip().splitlines() if ln.split() and abs(float(ln.split()[0]) * 1000 - wavelength_nm) < 1e-6)
    return n


def build_db(db_path):
    """Stages 1-5. Returns the build facts for the manifest."""
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    shutil.copy(BASE_DB, db_path)
    log = io.StringIO()
    merged = {}
    for name, mod, kw in family_jobs():
        with contextlib.redirect_stdout(log):
            rep = fam.run_family(name, mod.CSV_PATH, mod.SELECTIONS_PATH, db_path, fresh=False, load_physical_fn=fam.load_physical_properties, **kw)
        if rep.conflicts or rep.skipped or rep.warnings:
            raise ReleaseError(f"{name}: conflicts={rep.conflicts[:3]} skipped={rep.skipped[:3]} warnings={rep.warnings[:3]}")
        merged[name] = dict(inserted=dict(rep.inserted), unchanged=dict(rep.unchanged))
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    with conn:
        removed, orphans = dedupe_physical(conn)
        cross_source = rv.populate(conn)
        coverage = populate_descriptors(conn)
    source_repeats = validate(conn)
    conn.execute("VACUUM")
    conn.close()
    return dict(family_merges=merged, removed_duplicate_physical_rows=removed, removed_unreferenced_sources=orphans,
                descriptor_coverage=coverage, cross_source_validation=cross_source,
                optical_wavelengths_repeated_in_source=source_repeats)


# ---------------------------------------------------------------- packaging

def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args, cwd=_ROOT):
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def counts(db_path):
    conn = sqlite3.connect(f"{Path(db_path).as_uri()}?mode=ro", uri=True)
    tables = [t for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    table_rows = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    fam_of = {name: stem for name, (stem, _) in family_rows().items()}
    per_family = defaultdict(lambda: dict(materials=0, datasets=0, optical_rows=0, with_density=0))
    for mid, name in conn.execute("SELECT material_id, name FROM materials"):
        f = per_family[fam_of[name]]
        f["materials"] += 1
        f["datasets"] += conn.execute("SELECT COUNT(DISTINCT dataset_label) FROM optical_dispersion WHERE material_id = ?", (mid,)).fetchone()[0]
        f["optical_rows"] += conn.execute("SELECT COUNT(*) FROM optical_dispersion WHERE material_id = ?", (mid,)).fetchone()[0]
        f["with_density"] += conn.execute("SELECT COUNT(*) > 0 FROM physical_properties WHERE material_id = ? AND density_g_cm3 IS NOT NULL", (mid,)).fetchone()[0]
    datasets = conn.execute("SELECT COUNT(*) FROM (SELECT 1 FROM optical_dispersion GROUP BY material_id, dataset_label)").fetchone()[0]
    conn.close()
    return dict(tables=table_rows, datasets=datasets, per_family={k: per_family[k] for k in FAMILY_CSVS if k in per_family})


def export_csvs(db_path, out_dir):
    conn = sqlite3.connect(f"{Path(db_path).as_uri()}?mode=ro", uri=True)
    written = {}
    for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall():
        cur = conn.execute(f"SELECT * FROM {t}")
        header = [d[0] for d in cur.description]
        big = t == "optical_dispersion"
        path = out_dir / f"{t}.csv{'.gz' if big else ''}"
        with (gzip.open(path, "wt", newline="", compresslevel=9) if big else open(path, "w", newline="")) as f:
            w = csv.writer(f)
            w.writerow(header)
            n = 0
            for row in cur:
                w.writerow(row)
                n += 1
        written[path.name] = n
    conn.close()
    return written


def write_readme(path, version, facts, c, mp_version):
    fam_lines = "\n".join(f"| {k} | {v['materials']} | {v['datasets']} | {v['optical_rows']:,} | {v['with_density']} |" for k, v in c["per_family"].items())
    cov = facts["descriptor_coverage"]
    xs = facts["cross_source_validation"]
    n_mat = c["tables"]["materials"]
    path.write_text(f"""# materials-db v{version}

Optical constants (n, k), densities, x-ray and neutron scattering length densities, and compositional, structural and
molecular descriptors for **{n_mat} materials** (inorganic crystals and glasses, compound semiconductors, metals, polymers,
molecular liquids and biomolecules): {c['datasets']} optical datasets and {c['tables']['optical_dispersion']:,} optical
data points. All of it is in one SQLite file, `materials-db-v{version}.sqlite`, and every table is also exported as CSV in `csv/`.

Licence: **CC BY 4.0**. Cite this dataset and the upstream sources listed in `DATA_LICENSE.md` (refractiveindex.info,
Materials Project, PubChem, periodictable, pymatgen, RDKit).

## Contents by family

| family table | materials | optical datasets | optical rows | with a density |
|---|---|---|---|---|
{fam_lines}

A material in two family tables is counted once, under the first: the five nitrides batch 2 already held (AlN, h-BN, GaN, TiN,
VN) appear under batch2_31, so `nitrides` adds Si3N4 only.

`family_tables/` holds the build table of each family. Each row has a `flags` column recording every choice and its evidence:
which source, which Materials Project entry, disagreements between sources, and gaps. The database has no column for this.

## Tables

| table | rows | what it holds |
|---|---|---|
| materials | {c['tables']['materials']} | name (unique), formula, SMILES / InChIKey / CAS / PubChem CID where PubChem has the substance |
| optical_dispersion | {c['tables']['optical_dispersion']:,} | n and k against wavelength (nm). `dataset_label` = "phase \\| source \\| axis"; `raw_record_table` is the refractiveindex.info file each row came from |
| physical_properties | {c['tables']['physical_properties']} | density (g/cm3); x-ray SLD at Cu K-alpha and neutron SLD (thermal), in 1e-6 / A^2; `dataset_label` says whether a density is `MP_DFT` (calculated), `bulk_elemental_approximation` (a bulk value standing in for a film) or literature |
| sources | {c['tables']['sources']} | every citation (DOI where one exists) |
| chemical_descriptors | {c['tables']['chemical_descriptors']} | one row per material; see below |

## Descriptors (`chemical_descriptors`)

Every material has a row, and nothing is guessed or zero-filled. A descriptor that does not apply, or whose input is missing,
is NULL, and `descriptor_json` explains why.

- **compositional** ({cov.get('compositional', 0)}/{n_mat}): element-property statistics of the formula (mean, min, max,
  range and mean absolute deviation of atomic number, mass, Pauling electronegativity, period, group, Mendeleev number and
  atomic radius) plus stoichiometric norms. Polymers are described per repeat unit.
- **structural** ({cov.get('structural', 0)}/{n_mat}): space group, crystal system, conventional-cell lattice parameters, Z,
  cell volume, DFT density, energy above hull, formation energy and band gap. These come from Materials Project database
  {mp_version} and are **calculated, not measured**. `applies_to` says whether the entry is the material itself or only a
  crystalline reference for a film or amorphous sample.
- **molecular** ({cov.get('molecular', 0)}/{n_mat}): RDKit exact mass, TPSA, logP, rotatable bonds, H-bond donors and
  acceptors, aromatic rings and a Morgan fingerprint (radius 2, 2048 bits). These are computed on molecules (liquids and
  biomolecules, from PubChem's SMILES) and on polymer repeat units, each checked against the source's formula. They are not computed for inorganic solids, because those are not
  molecules; exact mass and heavy-atom count still come from their formula.

## How far the sources agree (`dataset_validation`, `consensus_properties`)

Datasets of one material are compared only like for like: same phase and optical axis (from `dataset_label`) and the same
temperature, over the wavelengths both cover, at their own data points (nothing extrapolated).

- **dataset_validation** ({sum(xs['pairs'].values())} comparisons over {xs['materials_compared']} materials): for each pair and for n
  (and k where both give it), the mean relative error, RMSE and Pearson r, classified `excellent` (< 2%), `warning` (< 10%) or
  `suspicious` (>= 10%); counts {xs['pairs']}. `notes` gives the overlap and whether each side is a measurement or a model
  fit of the dielectric function. For k the error is scaled to the largest k in the overlap; where k < 0.01 throughout, the
  absolute difference is used (excellent < 0.002, warning < 0.01).
- **consensus_properties** (n and k at 633 nm, per phase and axis, e.g. `n_633nm | wurtzite | o-ray`): the median of the
  MEASURED ambient-temperature datasets that cover 633 nm (model fits never vote), their standard deviation and count, a
  classification on the spread (max - min) / median with the thresholds above (`single_source` for one), and
  `confidence_score` = (1 - 0.5^sources) x (1 - spread / 10%), so one source scores 0.5 and a 5% spread halves the score;
  counts {xs['consensus']}. A material with only model fits at 633 nm (e.g. CdTe) has no consensus row.

## Calculated vs measured, and caveats

- DFT densities, all SLDs and all descriptors are calculated. Optical data are published measurements or fits to them.
- Several materials have more than one optical source. Each source is its own dataset; how far they agree is in
  `dataset_validation` and `consensus_properties` (above).
- Materials without a density (no reliable value) have no SLD. The family tables' `flags` say why.
- Known open items: GaSe is deferred (its formulas go non-physical inside their stated range). The SnSe alpha axis is
  excluded (the source data is not physical). PDCBT's recorded formula conflicts with its own name, so it has no formula
  descriptors. CS2's Chemnitz 2017 fit is excluded (same problem as GaSe). The legacy benchmark set is not included: water,
  ethanol and DMSO come from the liquids family instead; DPPC, BSA, PTFE, PEEK, nylon 6,6, PEG and polyethylenimine are not in
  refractiveindex.info; ITO is (other/In2O3-SnO2) and belongs with a later mixed-oxides batch.
- Semiconductors: several papers per material are loaded as separate datasets, including temperature series (e.g. GaAs at
  300-440 K and 600 degC, ZnGeP2 at 100-500 K; `optical_dispersion.temperature_c`). Ge2Sb2Te5 is deferred (its crystalline
  density needs a structure choice).
- Primary dataset (the family tables' n_633 / k_633) in the automatically selected families (halides, chalcogenides,
  liquids, semiconductors): measured data before model fits of the dielectric function, then the widest range covering
  633 nm. A page is a model fit only when its source says so (scripts/dataset_kind.py). Model datasets (e.g. Adachi's) are
  still loaded; CdTe, CdSe and PbSe have no measured data at 633 nm, so their primary n_633 is empty.
- Liquid densities carry their temperature (`physical_properties.temperature_c`). They come from the CIPM water formula, NIST
  reference equations of state, or PubChem records that are all physically consistent with each other; otherwise they are
  left empty.

## Files

`MANIFEST.json` has the build facts: git commit, refractiveindex.info commit, Materials Project database version, row counts
and every duplicate the build removed. `SHA256SUMS` lets you check the download (`shasum -a 256 -c SHA256SUMS`).
""")


def package(db_path, version, facts, out_root=None):
    out = Path(out_root or _ROOT / "release") / f"materials-db-v{version}"
    if out.exists():
        shutil.rmtree(out)  # always our own output folder under release/
    (out / "csv").mkdir(parents=True)
    (out / "family_tables").mkdir()
    (out / "descriptor_inputs").mkdir()
    sqlite_name = f"materials-db-v{version}.sqlite"
    shutil.copy(db_path, out / sqlite_name)
    csv_rows = export_csvs(out / sqlite_name, out / "csv")
    for stem in FAMILY_CSVS + GAP_CSVS:
        shutil.copy(_ROOT / "data" / f"{stem}.csv", out / "family_tables" / f"{stem}.csv")
    for f in DESCRIPTOR_INPUTS:
        shutil.copy(_ROOT / "data" / "descriptors" / f, out / "descriptor_inputs" / f)
    shutil.copy(_ROOT / "DATA_LICENSE.md", out / "DATA_LICENSE.md")
    c = counts(out / sqlite_name)
    mp_version = json.loads(rd.MP_CACHE.read_text())["mp_database_version"]
    write_readme(out / "README.md", version, facts, c, mp_version)
    import periodictable
    import pymatgen.core
    import rdkit
    manifest = dict(
        dataset="materials-db", version=version, license="CC-BY-4.0",
        built_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        git_commit=_git("rev-parse", "HEAD"), git_worktree_clean=_git("status", "--porcelain", "--untracked-files=no", "--", *BUILD_INPUTS) == "",
        refractiveindex_info_commit=_git("rev-parse", "HEAD", cwd=_ROOT / "refractiveindex_db"),
        materials_project_database_version=mp_version,
        software=dict(python=sys.version.split()[0], rdkit=rdkit.__version__, pymatgen=pymatgen.core.__version__, periodictable=periodictable.__version__),
        counts=c, csv_rows=csv_rows, **facts)
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1, default=str) + "\n")
    files = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (out / "SHA256SUMS").write_text("".join(f"{_sha256(p)}  {p.relative_to(out)}\n" for p in files))
    zpath = out.parent / f"{out.name}.zip"  # not with_suffix(): "v0.1.0" would lose ".0"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.rglob("*")):
            if p.is_file():
                z.write(p, Path(out.name) / p.relative_to(out))
    return out, zpath, manifest


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the downloadable materials-db release.")
    ap.add_argument("--version", required=True, help="e.g. 0.1.0")
    a = ap.parse_args(argv)
    work = _ROOT / "release" / f".build-{a.version}.sqlite"
    work.parent.mkdir(exist_ok=True)
    facts = build_db(work)
    out, zpath, manifest = package(work, a.version, facts)
    work.unlink()
    c = manifest["counts"]
    print(f"materials-db v{a.version}: {c['tables']['materials']} materials, {c['datasets']} datasets, {c['tables']['optical_dispersion']:,} optical rows, "
          f"{c['tables']['physical_properties']} physical rows; descriptors {facts['descriptor_coverage']}")
    print(f"removed {len(facts['removed_duplicate_physical_rows'])} duplicate physical rows, {len(facts['removed_unreferenced_sources'])} unreferenced sources")
    print(f"-> {out.relative_to(_ROOT)}/  and  {zpath.relative_to(_ROOT)} ({zpath.stat().st_size / 1e6:.1f} MB)")
    if not manifest["git_worktree_clean"]:
        print(f"WARNING: build inputs ({', '.join(BUILD_INPUTS)}) have uncommitted changes; build a published release from a clean commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
