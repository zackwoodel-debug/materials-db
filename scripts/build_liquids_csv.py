#!/usr/bin/env python3
"""
scripts/build_liquids_csv.py
=============================
Builds data/liquids.csv (oxides_50.csv column template + materialclass + selection_key + density_temperature_c) and
data/liquid_gaps.csv from data/step1_selections_liquids.json (run match_ri_info_liquids.py first).

Identity: PubChem by name; the returned formula must match the candidate's composition (deuterium counted as H, since PubChem writes
D2O as H2O), and the isotope composition read from PubChem's SMILES with RDKit must match exactly (so D2O cannot become H2O).

Density (a liquid's density is only meaningful at its temperature, so the temperature is stored with it):
  * water: the CIPM recommended formula (Tanaka et al., Metrologia 38, 301 (2001)) at the temperature of the primary optical dataset;
  * fluids NIST has a reference equation of state for (NIST Chemistry WebBook SRD 69): that model at the same temperature, 1 atm;
  * everything else: PubChem's experimental "Density" records. A record is used only if it states the value AND the temperature
    ("0.7893 g/cu cm at 20 degC", "13.534 @ 25 degC", or "1.100 at 20 degC/4 degC", a specific gravity against water at 4 degC);
    relative densities, ranges, bare numbers and values with fewer than 3 significant digits are never used. The value must be within
    10 degC of the optical data's temperature (20 degC when the page says "room temperature"), and its own temperature is stored.
    EVERY record must be physically consistent with every other (same temperature: equal within 0.25% + rounding; different
    temperatures: density falling by 0-0.25%/degC), because PubChem's sources copy one another and some carry a wrong temperature;
    any inconsistency leaves the density NULL with the conflicting records in the flags. The most precise record wins.
  * films and powders get the bulk (crystal) density labelled bulk_elemental_approximation; biomacromolecules get none.
No density is inferred, estimated or taken from Materials Project (a liquid has no crystal structure).
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_oxides_csv as base  # noqa: E402
from build_chalcogenides_csv import exact_formula_n633  # noqa: E402
from liquid_material_list import CANDIDATES, EXCLUDED_PAGES, OUT_OF_FAMILY  # noqa: E402
from materials_db.pipeline.process_condition import BULK_ELEMENTAL_APPROXIMATION  # noqa: E402

DATA = _ROOT / "data"
T_WINDOW_C = 10.0      # a density may be up to 10 degC from the optical data's temperature (its own temperature is stored)
MIN_SIG = 3            # records quoted to fewer significant digits ('0.79') are too coarse to use or to check with
SAME_T_REL = 0.0025    # two records at the same temperature (within 2 degC) must agree within 0.25% plus their rounding
MAX_ALPHA = 0.0025     # between temperatures a liquid's density must fall, by 0 to 0.25% per degC (organics ~0.1%/degC)
ROOM_T_C = 20.0
TANAKA = dict(doi="10.1088/0026-1394/38/4/3",
              title="Recommended table for the density of water between 0 C and 40 C based on recent experimental reports",
              authors="M. Tanaka, G. Girard, R. Davis, A. Peuto, N. Bignell", journal="Metrologia", year=2001)

_NUM = r"(\d+\.\d+)"
_T = r"(-?\d+(?:\.\d+)?)\s*°\s*C"
ABSOLUTE = re.compile(rf"^\s*{_NUM}\s*(?:g/cu\s*cm|g/cm3|g/cm\^3|g/cm³|g/ml|g/cc)\s*(?:at|@)\s*{_T}(?!\s*/)", re.I)
UNITLESS = re.compile(rf"^\s*{_NUM}\s*(?:@|at)\s*{_T}(?!\s*/)(?!\d)", re.I)
SG_4C = re.compile(rf"^\s*{_NUM}\s*(?:@|at)\s*{_T}\s*/\s*4\s*°\s*C", re.I)
CAMEO_F = re.compile(r"^\s*(\d+\.\d+)\s*at\s*(-?\d+(?:\.\d+)?)\s*°\s*F", re.I)  # USCG specific gravity: corroboration only
WATER_AT_4C = 0.999975


def tanaka_water_density(t_c):
    """CIPM formula for SMOW (Tanaka et al. 2001), g/cm3."""
    a1, a2, a3, a4, a5 = -3.983035, 301.797, 522528.9, 69.34881, 999.974950
    return a5 * (1 - (t_c + a1) ** 2 * (t_c + a2) / (a3 * (t_c + a4))) / 1000


def sig_digits(s):
    return len(s.replace(".", "").lstrip("0"))


def parse_density_records(pugview):
    """[(value g/cm3, temperature degC, source name, significant digits, raw text, usable_as_value)] from a PUG-View Density JSON."""
    refs = {r["ReferenceNumber"]: r.get("SourceName", "?") for r in pugview.get("Record", {}).get("Reference", [])}
    out = []

    def walk(sec):
        for s in sec.get("Section", []):
            walk(s)
        for info in sec.get("Information", []):
            src = refs.get(info.get("ReferenceNumber"), "?")
            for m in info.get("Value", {}).get("StringWithMarkup", []):
                raw = (m.get("String") or "").strip()
                if (g := SG_4C.match(raw)):
                    out.append((float(g.group(1)) * WATER_AT_4C, float(g.group(2)), src, sig_digits(g.group(1)), raw, True))
                elif (g := ABSOLUTE.match(raw) or UNITLESS.match(raw)):
                    out.append((float(g.group(1)), float(g.group(2)), src, sig_digits(g.group(1)), raw, True))
                elif (g := CAMEO_F.match(raw)):
                    out.append((float(g.group(1)), round((float(g.group(2)) - 32) * 5 / 9, 1), src, sig_digits(g.group(1)), raw, False))
    walk(pugview.get("Record", {}))
    return out


def _rounding(r):
    """Relative half-unit of the last printed digit ('1.34' -> 0.005 / 1.34), so rounding is never called a disagreement."""
    num = r[4].split()[0].rstrip("@")
    decimals = len(num.split(".")[1]) if "." in num else 0
    return 0.5 * 10 ** -decimals / r[0]


def consistent(a, b):
    """Could both records describe the same liquid? Same temperature: equal within 0.25% + rounding. Different temperatures:
    density falls with temperature at 0-0.25%/degC (+ rounding). PubChem's sources copy one another and sometimes carry the
    wrong temperature (HSDB and PAC give n-hexane 0.6606 at 25 degC, the 20 degC value), which is what this catches."""
    slack = _rounding(a) + _rounding(b)
    dt = b[1] - a[1]
    if abs(dt) < 2:  # too close to tell the sign of the change: equal within 0.25%, plus rounding, plus <= 0.25%/degC of expansion
        return abs(a[0] / b[0] - 1) <= SAME_T_REL + slack + MAX_ALPHA * abs(dt)
    lo, hi = (a, b) if dt > 0 else (b, a)
    alpha = (lo[0] - hi[0]) / (lo[0] * abs(dt))
    return -slack / abs(dt) <= alpha <= MAX_ALPHA + slack / abs(dt)


def choose_density(records, t_target):
    """Returns (value, temperature, source, raw, flags) or (None, None, None, None, reasons). Every usable record must be
    consistent with every other one; a single inconsistency leaves the density NULL (no record is trusted over another)."""
    from itertools import combinations
    recs = [r for r in records if r[3] >= MIN_SIG]
    usable = [r for r in recs if r[5] and abs(r[1] - t_target) <= T_WINDOW_C]
    if not usable:
        return None, None, None, None, [f"no PubChem density (>= {MIN_SIG} significant digits, stated temperature) within {T_WINDOW_C:g} degC "
                                        f"of {t_target:g} degC (records: {[r[4][:40] for r in records][:4]})"]
    bad = [(a, b) for a, b in combinations(recs, 2) if not consistent(a, b)]
    if bad:
        return None, None, None, None, ["PubChem density records are physically inconsistent (a wrong value or temperature label), so none is used: "
                                        + "; ".join(f"{a[2][:28]} '{a[4][:34]}' vs {b[2][:28]} '{b[4][:34]}'" for a, b in bad[:3])]
    best = max(usable, key=lambda r: (r[3], -abs(r[1] - t_target)))
    others = [r for r in recs if r is not best]
    flags = [f"density {best[0]:.6g} g/cm3 at {best[1]:g} degC from {best[2]} via PubChem ('{best[4]}')"]
    flags.append(f"consistent with {len(others)} other record(s): " + "; ".join(f"{r[2][:28]} '{r[4][:34]}'" for r in others[:3]) if others else
                 "single record: no second PubChem record to check it against")
    return best[0], best[1], best[2], best[4], flags


TRANSIENT = re.compile(r"exception|HTTP 5\d\d|rate-limited", re.I)
CACHE = base.RAW_CACHE / "liquids_pubchem_cache.json"  # gitignored read-through cache of SUCCESSFUL responses only


def _cache():
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def _cache_put(key, value):
    c = _cache()
    c[key] = value
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(c, indent=1, sort_keys=True))


def fetch_pubchem_retrying(mat, tries=4):
    """base.fetch_pubchem does not retry; PubChem answers 503 / times out now and then, which must not become a missing identity.
    Only successes are cached, so a rerun asks again for whatever failed."""
    key = f"identity|{mat['pubchem_name']}|{mat['formula']}"
    if key in _cache():
        return dict(_cache()[key], flags=list(_cache()[key]["flags"]))
    for attempt in range(tries):
        pc = base.fetch_pubchem(mat)
        if pc.get("pubchem_cid"):
            _cache_put(key, pc)
            return pc
        # under load PubChem also answers "not found" for names it knows, so that is retried like a 503
        if not any(TRANSIENT.search(f) or "not found" in f for f in pc["flags"]) or attempt == tries - 1:
            return pc
        time.sleep(5 * (attempt + 1))


def pugview_density(cid, tries=4):
    key = f"density|{cid}"
    if key in _cache():
        return _cache()[key]
    got = _pugview_density(cid, tries)
    if got:  # an empty answer (404) is never cached: it may be PubChem under load
        _cache_put(key, got)
    return got


def _pugview_density(cid, tries):
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug_view/data/compound/{cid}/JSON?heading=Density"
    for attempt in range(tries):
        time.sleep(base.PUBCHEM_RATE_DELAY)
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {}  # no Density section: a real "none", not an error
            if e.code < 500 and e.code != 429 or attempt == tries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries - 1:
                raise
        time.sleep(2 * (attempt + 1))


NIST = dict(doi="10.18434/T4D303", title="NIST Chemistry WebBook, NIST Standard Reference Database 69: Thermophysical Properties of Fluid Systems",
            authors="E. W. Lemmon, I. H. Bell, M. L. Huber, M. O. McLinden")
NIST_UA = {"User-Agent": "materials-db/0.1 (research dataset build)"}  # the WebBook answers 403 to Python's default agent


def nist_url(cas, t_c):
    return (f"https://webbook.nist.gov/cgi/fluid.cgi?Action=Data&Wide=on&ID=C{cas.replace('-', '')}&Type=IsoBar&Digits=6&P=0.101325"
            f"&THigh={t_c + 1:g}&TLow={t_c:g}&TInc=1&RefState=DEF&TUnit=C&PUnit=MPa&DUnit=g%2Fml&HUnit=kJ%2Fmol&WUnit=m%2Fs"
            "&VisUnit=uPa*s&STUnit=N%2Fm")


def nist_liquid_density(cas, t_c, tries=4):
    """Density (g/cm3) of the liquid at t_c and 1 atm from the reference equation of state in NIST SRD 69, or None when NIST
    has no model for this fluid. Successful answers are cached."""
    key = f"nist|{cas}|{t_c:g}"
    if key in _cache():
        return _cache()[key]
    for attempt in range(tries):
        try:
            txt = urllib.request.urlopen(urllib.request.Request(nist_url(cas, t_c), headers=NIST_UA), timeout=30).read().decode()
            break
        except urllib.error.HTTPError as e:
            if e.code == 400 and b"Query Error" in e.read():
                return None  # NIST has no equation of state for this fluid
            if attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))
    if not txt.startswith("Temperature"):
        return None  # "Query Error": NIST has no equation of state for this fluid (not cached: cheap to ask again)
    header = txt.splitlines()[0].split("\t")
    for line in txt.splitlines()[1:]:
        cells = line.split("\t")
        if abs(float(cells[0]) - t_c) < 1e-9 and cells[-1].strip() == "liquid":
            rho = float(cells[header.index("Density (g/ml)")])
            _cache_put(key, rho)
            return rho
    return None


def isotope_formula_ok(smiles, formula):
    """PubChem writes D2O as H2O; RDKit reads the isotopes from the SMILES, so D stays D."""
    from rdkit import Chem
    from rdkit.Chem.rdMolDescriptors import CalcMolFormula
    mol = Chem.MolFromSmiles(smiles) if smiles else None
    if mol is None:
        return False
    return base.parse_formula_counts(CalcMolFormula(mol, True, True)) == base.parse_formula_counts(formula)


def main():
    base.ensure_dirs()
    sel = json.loads((DATA / "step1_selections_liquids.json").read_text())
    matches = {c["key"]: c for c in json.loads((DATA / "liquid_ri_matches.json").read_text())["candidates"]}
    rows, gaps = [], []
    for i, c in enumerate(CANDIDATES, start=1):
        key, flags = c["key"], []
        m = matches[key]
        axes = sel[key]["axes"]
        first = axes[0]
        row = dict(idx=i, name=c["name"], formula=c["formula"], polymorph=None, materialclass=c["materialclass"], selection_key=key)
        if first["phase"] == "liquid":
            row["polymorph"] = "liquid"  # pairs the density with the liquid datasets, not the ice / supercooled ones

        # identity
        if c["pubchem_name"]:
            pc = fetch_pubchem_retrying(dict(idx=i, name=c["name"], formula=re.sub(r"D(?![a-z])", "H", c["formula"]), pubchem_name=c["pubchem_name"]))
            flags += pc.pop("flags")
            pc.pop("pubchem_formula_match", None)
            if pc.get("smiles") and not isotope_formula_ok(pc["smiles"], c["formula"]):
                flags.append(f"pubchem: SMILES {pc['smiles']} does not have the isotope composition {c['formula']} -- identifiers NULLed")
                pc = {k: None for k in pc}
            row.update(pc)
        else:
            flags.append("no single molecular formula (biomacromolecule): no PubChem identity, density or SLD")

        # density
        t_target = first["temperature_c"] if first["temperature_c"] is not None else ROOM_T_C
        sample = " ".join(a["comments"] for a in axes).lower()
        state = "film" if "film" in sample else "powder" if "powder" in sample else None
        if key == "H2O":
            row.update(density_g_cm3=round(tanaka_water_density(t_target), 6), density_temperature_c=t_target, density_source="literature",
                       density_citation_doi=TANAKA["doi"], density_citation_title=TANAKA["title"], density_citation_authors=TANAKA["authors"],
                       density_citation_journal=TANAKA["journal"], density_citation_year=TANAKA["year"],
                       density_citation_notes=f"CIPM formula for SMOW evaluated at {t_target:g} degC (the primary optical dataset's temperature).")
            flags.append(f"density = CIPM water formula at {t_target:g} degC (Tanaka et al. 2001), not a PubChem record "
                         "(HSDB's 0.9950 g/cm3 at 25 degC is 0.2% below the metrological value)")
        elif row.get("cas_number") and state is None and (rho := nist_liquid_density(row["cas_number"], t_target)) is not None:
            url = nist_url(row["cas_number"], t_target)
            row.update(density_g_cm3=round(rho, 6), density_temperature_c=t_target, density_source="literature",
                       density_citation_doi=NIST["doi"], density_citation_title=NIST["title"], density_citation_authors=NIST["authors"],
                       density_citation_notes=f"Reference equation of state for {c['name']} (CAS {row['cas_number']}) at {t_target:g} degC, "
                                              f"0.101325 MPa: {url}")
            flags.append(f"density = NIST SRD 69 reference equation of state at {t_target:g} degC and 1 atm (the primary optical "
                         "dataset's temperature); preferred over PubChem records")
            try:  # the PubChem records are still read, as a cross-check that is recorded
                pv, pt, psrc, praw, _ = choose_density(parse_density_records(pugview_density(row["pubchem_cid"])), t_target)
                flags.append(f"PubChem cross-check: {pv} g/cm3 at {pt:g} degC ({psrc})" if pv else
                             "PubChem cross-check: no consistent PubChem record")
            except Exception:
                pass
        elif row.get("pubchem_cid"):
            try:
                recs = parse_density_records(pugview_density(row["pubchem_cid"]))
            except Exception as e:
                recs = []
                base.quarantine("pubchem", f"{key}_density", f"density lookup failed: {type(e).__name__}: {e}", None)
                flags.append(f"PubChem density lookup failed ({type(e).__name__}); quarantined")
            value, t, src, raw, dflags = choose_density(recs, t_target)
            flags += dflags
            if value is not None:
                row.update(density_g_cm3=round(value, 6), density_temperature_c=t,
                           density_source=BULK_ELEMENTAL_APPROXIMATION if state else "literature",
                           density_citation_title=f"{src} via PubChem CID {row['pubchem_cid']}: density of {c['name']}",
                           density_citation_notes=f"PubChem record text: '{raw}'. https://pubchem.ncbi.nlm.nih.gov/compound/{row['pubchem_cid']}")
                if state:
                    flags.append(f"sample is a {state}: the bulk density stands in for it (labelled bulk_elemental_approximation)")
        if row.get("density_g_cm3") is None and c["formula"]:
            gaps.append(dict(key=key, name=c["name"], gap_kind="density", reason=" / ".join(f for f in flags if "density" in f.lower() or "PubChem" in f)[-400:]))

        row["xray_energy_ev"] = base.XRAY_ENERGY_KEV * 1000
        if c["formula"]:
            sld = base.compute_sld(c["formula"], row.get("density_g_cm3"))
            flags += sld.pop("flags")
            row.update(sld)
            row["strong_neutron_absorber"] = base.strong_neutron_absorber(c["formula"])

        # optical: primary paper's axes -> columns; other papers (same phase and axis) -> evidence in flags
        row.update(ri_shelf=c["shelf"], ri_book=c["book"], ri_page_primary=first["page"], axis_primary=first["axis"])
        same = lambda a: (a["phase"], a["tag"]) == (first["phase"], first["tag"])
        primary_paper = [a for a in axes if same(a)]
        for j, a in enumerate(primary_paper[:3], start=1):
            interp = base.interpolate_axis(a["data_path"])
            flags += [f"[{a['page']}] {f}" for f in interp.pop("flags")]
            n633 = exact_formula_n633(a["data_path"], interp["n_633"])
            if j == 1:
                row["n_633"], row["k_633"] = n633, interp["k_633"]
                row["ri_wl_min_nm"], row["ri_wl_max_nm"] = interp["wl_min_nm"], interp["wl_max_nm"]
            else:
                row.update({f"axis_{j}": a["axis"], f"n_633_axis{j}": n633, f"k_633_axis{j}": interp["k_633"], f"ri_page_axis{j}": a["page"]})
        ref = row.get("n_633")
        for a in axes:
            if same(a):
                continue
            interp = base.interpolate_axis(a["data_path"])
            interp.pop("flags")
            n633 = exact_formula_n633(a["data_path"], interp["n_633"])
            flags.append(f"additional dataset {a['dataset_label']}"
                         + (f" ({a['temperature_c']:g} degC)" if a["temperature_c"] is not None else "") + f": n(633 nm)={n633}")
            if n633 is not None and ref and a["phase"] == first["phase"] and a["axis"] == first["axis"] and abs(n633 / ref - 1) > 0.02:
                flags.append(f"SOURCES DISAGREE at 633 nm by {abs(n633 / ref - 1) * 100:.1f}% ({first['dataset_label']} {ref:.4f} vs "
                             f"{a['dataset_label']} {n633:.4f}); both kept, none preferred on quality")
        if len(axes) > len(primary_paper):
            flags.append(f"{len(axes)} datasets loaded; n_633/k_633 columns are the primary ({first['dataset_label']}, widest span covering 633 nm)")
        from match_ri_info_liquids import temperature_c as text_temperature
        for a in axes:
            said = text_temperature(a["comments"])
            if said is not None and a["temperature_c"] is not None and abs(said - a["temperature_c"]) > 1.0:
                flags.append(f"[{a['page']}] the page text says {said:g} degC but its CONDITIONS field says {a['temperature_c']:g} degC "
                             "(stored, as for every page); a refractiveindex.info inconsistency")
        for a in axes:
            if re.search(r"\bisopropanol\b", a["comments"], re.I) and key not in ("2-C3H7OH",):
                flags.append(f"[{a['page']}] the page's COMMENTS say 'Isopropanol' (a copy error in refractiveindex.info); its title and book identify {c['name']}")
        if m.get("about_yml_formula_matches") is False:
            flags.append(f"refractiveindex.info about.yml for this book lists the formula {m['about_yml_formula']} (a copy error); "
                         "the catalog title, folder name and data identify the compound")
        for p in m.get("excluded_pages", []):
            flags.append(f"page {p} NOT loaded: {EXCLUDED_PAGES[(c['shelf'], c['book'], p)]}")
        if m.get("k_only_pages"):
            flags.append(f"k-only page(s) {m['k_only_pages']} listed but not loaded (no n)")
        if c["note"]:
            flags.append(c["note"])
        row["flags"] = base.FLAG_JOIN.join(flags)
        rows.append(row)

    template = list(pd.read_csv(DATA / "oxides_50.csv", nrows=0).columns)
    df = pd.DataFrame(rows)
    df = df.reindex(columns=template + [col for col in df.columns if col not in template])
    df.to_csv(DATA / "liquids.csv", index=False)
    for (shelf, book, page), why in EXCLUDED_PAGES.items():
        gaps.append(dict(key=f"{shelf}/{book}/{page}", name=f"{book} page {page}", gap_kind="excluded_page", reason=why))
    for k, why in OUT_OF_FAMILY.items():
        gaps.append(dict(key=k, name=k, gap_kind="out_of_family", reason=why))
    pd.DataFrame(gaps).to_csv(DATA / "liquid_gaps.csv", index=False)
    print(f"Wrote liquids.csv: {len(df)} rows x {len(df.columns)} cols; liquid_gaps.csv: {len(gaps)} rows; "
          f"with density: {df['density_g_cm3'].notna().sum()}/{len(df)}")


if __name__ == "__main__":
    main()
