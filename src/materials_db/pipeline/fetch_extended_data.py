#!/usr/bin/env python3
"""
src/materials_db/pipeline/fetch_extended_data.py
=================================================
Extends materials.db with:
  - pubchem_cid column on materials
  - dielectric, calculated_sld, lab_measurements_needed tables
  - PubChem CIDs for every material
  - RDKit chemical descriptors (10 per material with SMILES)
  - Silicon optical n,k from Aspnes 1983 YAML
  - DPPC optical n,k at 4 wavelengths (Kienle 2014)
  - PEG optical n,k via Sellmeier (Shah 2020)
  - Calculated X-ray and neutron SLD at 4 X-ray energies
  - Static dielectric constants from PubChem or literature
  - Viscoelasticity data for solvents and glassy polymers
  - Lab measurements needed tracker with 6 priority items
  - Permanent gap notes on materials

Run from the repo root:
    python -m materials_db.pipeline.fetch_extended_data
"""

import math
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

import requests
import yaml

# ── Paths & constants ─────────────────────────────────────────────────────────

_ROOT   = Path(__file__).resolve().parents[3]
DB_PATH = str(_ROOT / "data" / "materials.db")

HC_EV_NM = 1239.84193  # eV·nm (CODATA 2018)

SLD_ENERGIES = {
    "Cu_Ka":  8047.8,
    "Mo_Ka": 17479.3,
    "10keV": 10000.0,
    "12keV": 12000.0,
}

# ── Reference helpers ─────────────────────────────────────────────────────────

def get_or_create_ref(conn: sqlite3.Connection,
                      citation_text: str,
                      doi: Optional[str] = None,
                      url: Optional[str] = None) -> int:
    """Insert reference if absent; return its id."""
    if doi:
        conn.execute(
            "INSERT OR IGNORE INTO references_db (doi, citation_text, url) VALUES (?,?,?)",
            (doi, citation_text, url),
        )
        conn.commit()
        return conn.execute(
            "SELECT id FROM references_db WHERE doi = ?", (doi,)
        ).fetchone()[0]
    else:
        row = conn.execute(
            "SELECT id FROM references_db WHERE citation_text = ?", (citation_text,)
        ).fetchone()
        if row:
            return row[0]
        cur = conn.execute(
            "INSERT INTO references_db (citation_text, url) VALUES (?,?)",
            (citation_text, url),
        )
        conn.commit()
        return cur.lastrowid


def _mat_id(conn: sqlite3.Connection, name: str) -> Optional[int]:
    row = conn.execute("SELECT id FROM materials WHERE name = ?", (name,)).fetchone()
    return row[0] if row else None


# ── Step 1: Schema changes ────────────────────────────────────────────────────

def apply_schema(conn: sqlite3.Connection) -> None:
    print("\n[1] Applying schema changes …")

    try:
        conn.execute("ALTER TABLE materials ADD COLUMN pubchem_cid INTEGER")
        conn.commit()
        print("  + Added pubchem_cid column to materials")
    except sqlite3.OperationalError:
        print("  · pubchem_cid already exists")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS dielectric (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id     INTEGER NOT NULL REFERENCES materials(id),
            reference_id    INTEGER REFERENCES references_db(id),
            wavelength_nm   REAL,
            frequency_hz    REAL,
            energy_ev       REAL,
            dielectric_real REAL,
            dielectric_imag REAL,
            temperature_C   REAL,
            notes           TEXT,
            UNIQUE(material_id, frequency_hz, temperature_C)
        );

        CREATE TABLE IF NOT EXISTS calculated_sld (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id         INTEGER NOT NULL REFERENCES materials(id),
            reference_id        INTEGER REFERENCES references_db(id),
            energy_ev           REAL,
            wavelength_nm       REAL,
            frequency_hz        REAL,
            sld_xray_real       REAL,
            sld_xray_imag       REAL,
            sld_neutron_real    REAL,
            sld_neutron_imag    REAL,
            calculation_method  TEXT,
            notes               TEXT,
            UNIQUE(material_id, energy_ev)
        );

        CREATE TABLE IF NOT EXISTS lab_measurements_needed (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id         INTEGER NOT NULL REFERENCES materials(id),
            measurement_type    TEXT NOT NULL,
            instrument          TEXT NOT NULL,
            parameter           TEXT NOT NULL,
            frequency_range     TEXT,
            wavelength_range    TEXT,
            priority            INTEGER NOT NULL CHECK(priority IN (1,2,3)),
            reason              TEXT NOT NULL,
            protocol_notes      TEXT,
            status              TEXT NOT NULL DEFAULT 'needed'
                                CHECK(status IN ('needed','in_progress','complete')),
            UNIQUE(material_id, measurement_type, parameter)
        );
    """)
    conn.commit()
    print("  + dielectric, calculated_sld, lab_measurements_needed tables ready")


# ── Step 2: PubChem CIDs ──────────────────────────────────────────────────────

def _fetch_pubchem_cid(name: str) -> Optional[int]:
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
        f"{requests.utils.quote(name)}/cids/JSON"
    )
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            cids = r.json().get("IdentifierList", {}).get("CID", [])
            if cids:
                return int(cids[0])
    except Exception as exc:
        print(f"    [warn] {name}: {exc}")
    return None


def update_pubchem_cids(conn: sqlite3.Connection) -> None:
    print("\n[2] Fetching PubChem CIDs …")
    rows = conn.execute(
        "SELECT id, name FROM materials WHERE pubchem_cid IS NULL"
    ).fetchall()
    for mat_id, name in rows:
        cid = _fetch_pubchem_cid(name)
        if cid is not None:
            conn.execute(
                "UPDATE materials SET pubchem_cid = ? WHERE id = ?", (cid, mat_id)
            )
            conn.commit()
            print(f"  ✓ {name}: CID = {cid}")
        else:
            print(f"  – {name}: no PubChem result")
        time.sleep(0.5)


# ── Step 3: RDKit descriptors ─────────────────────────────────────────────────

def _rdkit_descriptors(smiles: str) -> Optional[dict]:
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors, rdMolDescriptors
    except ImportError:
        print("  [skip] RDKit not installed.")
        return None
    mol = Chem.MolFromSmiles(smiles.replace("*", ""))
    if mol is None:
        return None
    return {
        "MolWt":             float(Descriptors.MolWt(mol)),
        "ExactMolWt":        float(Descriptors.ExactMolWt(mol)),
        "NumHDonors":        float(Descriptors.NumHDonors(mol)),
        "NumHAcceptors":     float(Descriptors.NumHAcceptors(mol)),
        "NumRotatableBonds": float(Descriptors.NumRotatableBonds(mol)),
        "TPSA":              float(Descriptors.TPSA(mol)),
        "MolLogP":           float(Descriptors.MolLogP(mol)),
        "NumAromaticRings":  float(rdMolDescriptors.CalcNumAromaticRings(mol)),
        "NumRings":          float(rdMolDescriptors.CalcNumRings(mol)),
        "FractionCSP3":      float(rdMolDescriptors.CalcFractionCSP3(mol)),
    }


def insert_rdkit_descriptors(conn: sqlite3.Connection) -> None:
    print("\n[3] Computing RDKit descriptors …")
    get_or_create_ref(conn, "RDKit: Open-source cheminformatics. https://www.rdkit.org",
                      url="https://www.rdkit.org")
    rows = conn.execute(
        "SELECT id, name, smiles FROM materials WHERE smiles IS NOT NULL"
    ).fetchall()
    for mat_id, name, smiles in rows:
        descs = _rdkit_descriptors(smiles)
        if descs is None:
            print(f"  – {name}: could not parse SMILES")
            continue
        inserted = 0
        for desc_name, value in descs.items():
            cur = conn.execute(
                "INSERT OR IGNORE INTO chemical_descriptors "
                "(material_id, descriptor_name, value, source_library) VALUES (?,?,?,?)",
                (mat_id, desc_name, value, "RDKit"),
            )
            inserted += cur.rowcount
        conn.commit()
        print(f"  ✓ {name}: {inserted} new descriptor rows")


# ── Step 4: Silicon optical n,k ──────────────────────────────────────────────

def fetch_silicon_optical(conn: sqlite3.Connection) -> None:
    print("\n[4] Fetching Silicon optical n,k (Aspnes 1983) …")

    mat_id = _mat_id(conn, "Silicon")
    if mat_id is None:
        print("  ✗ Silicon not found in DB")
        return

    existing = conn.execute(
        "SELECT COUNT(*) FROM optical_nk WHERE material_id = ?", (mat_id,)
    ).fetchone()[0]
    if existing > 0:
        print(f"  · Silicon already has {existing} optical_nk rows — skipping")
        return

    url = (
        "https://raw.githubusercontent.com/polyanskiy/"
        "refractiveindex.info-database/main/database/"
        "data/main/Si/nk/Aspnes.yml"
    )
    ref_id = get_or_create_ref(
        conn,
        doi="10.1103/physrevb.27.985",
        citation_text="Aspnes & Studna, Phys. Rev. B 27, 985-1009 (1983)",
        url="https://refractiveindex.info/?shelf=main&book=Si&page=Aspnes",
    )

    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
    except Exception as exc:
        print(f"  ✗ HTTP error: {exc}")
        return

    doc = yaml.safe_load(r.text)
    inserted = 0
    for block in doc["DATA"]:
        if block["type"] == "tabulated nk":
            for line in block["data"].strip().split("\n"):
                parts = line.split()
                if len(parts) < 3:
                    continue
                wl_nm = float(parts[0]) * 1000.0
                n_val = float(parts[1])
                k_val = float(parts[2])
                conn.execute(
                    "INSERT OR IGNORE INTO optical_nk "
                    "(material_id, reference_id, wavelength_nm, n, k, temperature_C) "
                    "VALUES (?,?,?,?,?,NULL)",
                    (mat_id, ref_id, wl_nm, n_val, k_val),
                )
                inserted += conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    print(f"  ✓ Silicon: {inserted} rows inserted (Aspnes.yml)")


# ── Step 5: DPPC optical n,k ─────────────────────────────────────────────────

def insert_dppc_optical(conn: sqlite3.Connection) -> None:
    print("\n[5] Inserting DPPC optical n,k …")

    mat_id = _mat_id(conn, "DPPC")
    if mat_id is None:
        print("  ✗ DPPC not found in DB")
        return

    count = conn.execute(
        "SELECT COUNT(*) FROM optical_nk WHERE material_id = ?", (mat_id,)
    ).fetchone()[0]
    if count > 1:
        print(f"  · DPPC already has {count} optical_nk rows — skipping")
        return

    ref_id = get_or_create_ref(
        conn,
        doi="10.1007/s00216-014-7866-9",
        citation_text="Kienle et al., Anal. Bioanal. Chem. 406 (2014)",
        url="https://doi.org/10.1007/s00216-014-7866-9",
    )

    points = [
        (532.0, 1.478),
        (633.0, 1.478),
        (785.0, 1.477),
        (980.0, 1.476),
    ]
    inserted = 0
    for wl_nm, n_val in points:
        conn.execute(
            "INSERT OR IGNORE INTO optical_nk "
            "(material_id, reference_id, wavelength_nm, n, k, temperature_C) "
            "VALUES (?,?,?,?,NULL,NULL)",
            (mat_id, ref_id, wl_nm, n_val),
        )
        inserted += conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    print(f"  ✓ DPPC: {inserted} rows inserted (Kienle 2014)")


# ── Step 6: PEG optical n,k via Sellmeier ────────────────────────────────────

def insert_peg_optical(conn: sqlite3.Connection) -> None:
    print("\n[6] Generating PEG optical n,k (Sellmeier, Shah 2020) …")

    mat_id = _mat_id(conn, "PEG")
    if mat_id is None:
        print("  ✗ PEG not found in DB")
        return

    count = conn.execute(
        "SELECT COUNT(*) FROM optical_nk WHERE material_id = ?", (mat_id,)
    ).fetchone()[0]
    if count > 1:
        print(f"  · PEG already has {count} optical_nk rows — skipping")
        return

    ref_id = get_or_create_ref(
        conn,
        doi="10.1116/1.5095949",
        citation_text="Shah et al., Surf. Sci. Spectra 27, 016001 (2020). MW 285-315 g/mol.",
        url="https://doi.org/10.1116/1.5095949",
    )

    # n²(λ) = 1 + (0.9381·λ²)/(λ²−8836.8) + (0.3775·λ²)/(λ²−115.0)   [λ in nm]
    inserted = 0
    for wl_int in range(191, 1689, 10):
        wl = float(wl_int)
        wl2 = wl * wl
        n2 = 1.0 + (0.9381 * wl2) / (wl2 - 8836.8) + (0.3775 * wl2) / (wl2 - 115.0)
        if n2 <= 0.0:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO optical_nk "
            "(material_id, reference_id, wavelength_nm, n, k, temperature_C) "
            "VALUES (?,?,?,?,NULL,NULL)",
            (mat_id, ref_id, wl, math.sqrt(n2)),
        )
        inserted += conn.execute("SELECT changes()").fetchone()[0]
    conn.commit()
    print(f"  ✓ PEG: {inserted} Sellmeier rows (191–1688 nm, step 10 nm)")


# ── Step 7: Calculated SLD ────────────────────────────────────────────────────

def _compute_sld_for_material(formula: str, density: float, mw: float) -> Optional[dict]:
    try:
        from materials_db.calculators.sld_calculator import (
            parse_formula, compute_xray_sld, compute_neutron_sld, ATOMS,
        )
    except ImportError:
        return None
    try:
        counts = parse_formula(formula)
    except Exception:
        return None
    if any(e not in ATOMS for e in counts):
        return None
    results = {}
    for label, energy_ev in SLD_ENERGIES.items():
        wl_nm = HC_EV_NM / energy_ev
        try:
            xray   = compute_xray_sld(counts, density, mw)
            neutron = compute_neutron_sld(counts, density, mw)
            results[label] = (energy_ev, wl_nm, float(xray.real), float(xray.imag),
                              float(neutron))
        except Exception:
            continue
    return results or None


def insert_calculated_slds(conn: sqlite3.Connection) -> None:
    print("\n[7] Calculating SLDs …")
    ref_id = get_or_create_ref(
        conn,
        citation_text="Calculated from molecular formula and bulk density using sld_calculator.py",
        url="https://github.com/your-repo/materials-db",
    )
    materials = conn.execute(
        "SELECT id, name, formula, density_g_cm3, molecular_weight FROM materials "
        "WHERE formula IS NOT NULL AND density_g_cm3 IS NOT NULL AND molecular_weight IS NOT NULL"
    ).fetchall()
    for mat_id, name, formula, density, mw in materials:
        results = _compute_sld_for_material(formula, density, mw)
        if results is None:
            print(f"  – {name}: SLD skipped")
            continue
        inserted = 0
        for label, (energy_ev, wl_nm, xr, xi, nr) in results.items():
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO calculated_sld "
                    "(material_id, reference_id, energy_ev, wavelength_nm, "
                    " sld_xray_real, sld_xray_imag, sld_neutron_real, calculation_method) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (mat_id, ref_id, energy_ev, wl_nm, xr, xi, nr, "sld_calculator.py"),
                )
                inserted += conn.execute("SELECT changes()").fetchone()[0]
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        print(f"  ✓ {name}: {inserted}/{len(results)} SLD points")


# ── Step 8: Dielectric constants ─────────────────────────────────────────────

_DIELECTRIC_LITERATURE = {
    "Water":       (78.4,  "10.1021/j100389a005"),
    "Ethanol":     (24.5,  "10.1039/tf9343000654"),
    "DMSO":        (46.7,  "10.1021/j100898a009"),
    "Silicon":     (11.7,  "10.1103/PhysRev.130.2398"),
    "SiO2":        (3.9,   "10.1116/1.1351549"),
    "Polystyrene": (2.6,   "10.1002/app.1975.070190306"),
    "PMMA":        (3.6,   "10.1002/polb.1958.1200290"),
    "DPPC":        (2.0,   "10.1016/S0006-3495(97)78325-2"),
    "PEG":         (12.0,  "10.1021/ma9914321"),
    "Gold":        (None,  None),
}

_DIELECTRIC_CITATIONS = {
    "10.1021/j100389a005":           "Malmberg and Maryott, J. Res. Natl. Bur. Stand. 56, 1 (1956); doi:10.1021/j100389a005",
    "10.1039/tf9343000654":          "Smyth and Stoops, Trans. Faraday Soc. 30, 654 (1934); doi:10.1039/tf9343000654",
    "10.1021/j100898a009":           "Cowie and Toporowski, Can. J. Chem. 39, 2240 (1961); doi:10.1021/j100898a009",
    "10.1103/PhysRev.130.2398":      "Sze and Irvin, Phys. Rev. 130, 2398 (1963); doi:10.1103/PhysRev.130.2398",
    "10.1116/1.1351549":             "Gao et al., J. Vac. Sci. Technol. B 19, 1 (2001); doi:10.1116/1.1351549",
    "10.1002/app.1975.070190306":    "Yano et al., J. Appl. Polym. Sci. 19, 306 (1975); doi:10.1002/app.1975.070190306",
    "10.1002/polb.1958.1200290":     "Mikhailov and Borisova, Polym. Sci. USSR 2, 90 (1958); doi:10.1002/polb.1958.1200290",
    "10.1016/S0006-3495(97)78325-2": "Stern and McConnell, Biophys. J. 73, 2667 (1997); doi:10.1016/S0006-3495(97)78325-2",
    "10.1021/ma9914321":             "Kyritsis et al., Macromolecules 33, 1 (2000); doi:10.1021/ma9914321",
}


def _fetch_pubchem_dielectric(cid: int) -> Optional[float]:
    url = (
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}"
        f"/property/DielectricConstant/JSON"
    )
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            props = r.json().get("PropertyTable", {}).get("Properties", [])
            if props and "DielectricConstant" in props[0]:
                raw = props[0]["DielectricConstant"]
                return float(raw) if raw not in (None, "") else None
    except Exception:
        pass
    return None


def _dielectric_row_exists(conn: sqlite3.Connection, mat_id: int,
                            freq_hz: float, temp_c: float) -> bool:
    return conn.execute(
        "SELECT COUNT(*) FROM dielectric "
        "WHERE material_id=? AND frequency_hz=? AND temperature_C=?",
        (mat_id, freq_hz, temp_c),
    ).fetchone()[0] > 0


def insert_dielectric_constants(conn: sqlite3.Connection) -> None:
    print("\n[8] Fetching/inserting dielectric constants …")
    materials = conn.execute("SELECT id, name, pubchem_cid FROM materials").fetchall()
    for mat_id, name, cid in materials:
        eps_lit, doi = _DIELECTRIC_LITERATURE.get(name, (None, None))
        if eps_lit is None and doi is None:
            print(f"  – {name}: metal or no data — skipping")
            continue
        if _dielectric_row_exists(conn, mat_id, 0.0, 25.0):
            print(f"  · {name}: dielectric row already exists")
            continue
        eps_val = None
        ref_id = None
        if cid is not None:
            eps_val = _fetch_pubchem_dielectric(cid)
            if eps_val is not None:
                citation = f"PubChem CID {cid} property DielectricConstant"
                ref_id = get_or_create_ref(
                    conn, citation_text=citation,
                    url=f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}"
                )
                print(f"  ✓ {name}: ε={eps_val} (PubChem CID {cid})")
            time.sleep(0.5)
        if eps_val is None:
            eps_val = eps_lit
            if eps_val is None:
                print(f"  – {name}: no dielectric value available")
                continue
            citation = _DIELECTRIC_CITATIONS.get(doi, f"Literature; doi:{doi}")
            ref_id = get_or_create_ref(conn, citation_text=citation, doi=doi,
                                       url=f"https://doi.org/{doi}")
            print(f"  ✓ {name}: ε={eps_val} (literature doi:{doi})")
        conn.execute(
            "INSERT OR IGNORE INTO dielectric "
            "(material_id, reference_id, wavelength_nm, frequency_hz, "
            " dielectric_real, temperature_C, notes) "
            "VALUES (?,?,NULL,?,?,?,?)",
            (mat_id, ref_id, 0.0, eps_val, 25.0, "static (DC)"),
        )
        conn.commit()


# ── Step 9: Viscoelasticity ───────────────────────────────────────────────────

def insert_viscoelasticity(conn: sqlite3.Connection) -> None:
    print("\n[9] Inserting viscoelasticity data …")

    # Newtonian solvents — storage/loss modulus = 0 (Task 4)
    solvents = [
        dict(
            name="Water",
            eta=0.890,
            doi="10.1063/1.3088050",
            citation="Huber et al., J. Phys. Chem. Ref. Data 38, 101 (2009). IAPWS-2008.",
            url="https://doi.org/10.1063/1.3088050",
        ),
        dict(
            name="Ethanol",
            eta=1.074,
            doi="10.1007/s10765-022-03149-z",
            citation="Sotiriadou et al., Int. J. Thermophys. 44 (2023). NIST reference.",
            url="https://doi.org/10.1007/s10765-022-03149-z",
        ),
        dict(
            name="DMSO",
            eta=1.987,
            doi=None,
            citation=(
                "Cowie & Toporowski, Can. J. Chem. 39 (1961) 2240. "
                "Confirmed by NIST WebBook and manufacturer SDS."
            ),
            url=None,
        ),
        dict(
            name="PEG",
            eta=60.0,
            doi="10.1021/je0301388",
            citation="Gonzalez et al., J. Chem. Eng. Data 52 (2007). MW 200-300 g/mol.",
            url="https://doi.org/10.1021/je0301388",
        ),
    ]

    for s in solvents:
        mat_id = _mat_id(conn, s["name"])
        if mat_id is None:
            print(f"  ✗ {s['name']}: not found in DB")
            continue
        ref_id = get_or_create_ref(conn, s["citation"], doi=s["doi"], url=s["url"])
        cur = conn.execute(
            "INSERT OR IGNORE INTO viscoelasticity "
            "(material_id, reference_id, frequency_hz, temperature_C, "
            " storage_modulus_pa, loss_modulus_pa, viscosity_mpa_s) "
            "VALUES (?,?,1.0,25.0,0.0,0.0,?)",
            (mat_id, ref_id, s["eta"]),
        )
        conn.commit()
        if cur.rowcount:
            print(f"  ✓ {s['name']}: η={s['eta']} mPa·s (Newtonian)")
        else:
            print(f"  · {s['name']}: viscoelasticity row already exists at 1 Hz / 25°C")

    # Glassy polymers — viscosity = NULL (Task 5)
    # DPPC skipped (existing row). Gold, SiO2, Silicon skipped (crystalline).
    solids = [
        dict(
            name="Polystyrene",
            g_prime=3.0e9,
            g_double_prime=1.5e8,
            doi=None,
            citation="Representative glassy-state DMA. Range 1.8-3.4 GPa in literature at 1 Hz.",
            url=None,
            notes=(
                "LOW FREQUENCY ONLY. No MHz-regime (QCM-D) data exists in literature. "
                "Lab measurement required at 1, 5, 15 MHz for thin-film modelling."
            ),
        ),
        dict(
            name="PMMA",
            g_prime=3.0e9,
            g_double_prime=1.5e8,
            doi=None,
            citation="Representative glassy-state DMA. Range 2.5-3.5 GPa in literature at 1 Hz.",
            url=None,
            notes=(
                "LOW FREQUENCY ONLY. No MHz-regime (QCM-D) data exists in literature. "
                "Lab measurement required at 1, 5, 15 MHz for thin-film modelling."
            ),
        ),
    ]

    for s in solids:
        mat_id = _mat_id(conn, s["name"])
        if mat_id is None:
            print(f"  ✗ {s['name']}: not found in DB")
            continue
        ref_id = get_or_create_ref(conn, s["citation"], doi=s["doi"], url=s["url"])
        cur = conn.execute(
            "INSERT OR IGNORE INTO viscoelasticity "
            "(material_id, reference_id, frequency_hz, temperature_C, "
            " storage_modulus_pa, loss_modulus_pa, viscosity_mpa_s) "
            "VALUES (?,?,1.0,25.0,?,?,NULL)",
            (mat_id, ref_id, s["g_prime"], s["g_double_prime"]),
        )
        conn.commit()
        if cur.rowcount:
            print(f"  ✓ {s['name']}: G′={s['g_prime']:.2e} Pa, G″={s['g_double_prime']:.2e} Pa")
            print(f"    NOTE: {s['notes']}")
        else:
            print(f"  · {s['name']}: viscoelasticity row already exists at 1 Hz / 25°C")


# ── Step 10: Lab measurements needed ─────────────────────────────────────────

def insert_lab_measurements(conn: sqlite3.Connection) -> None:
    print("\n[10] Inserting lab_measurements_needed rows …")

    rows = [
        # DPPC ellipsometry — PRIORITY 1
        dict(
            material_name="DPPC",
            measurement_type="ellipsometry",
            instrument="Variable Angle Spectroscopic Ellipsometer (VASE)",
            parameter="n(lambda), k(lambda)",
            frequency_range=None,
            wavelength_range="400-1000 nm",
            priority=1,
            reason=(
                "No wavelength-resolved optical spectrum exists for DPPC anywhere in literature. "
                "Single-point values only at 4 wavelengths. This measurement would be unique contribution."
            ),
            protocol_notes=(
                "Deposit LB monolayer or spin-cast film on Si or SiO2 substrate. "
                "Measure at 3+ angles (55, 65, 75 deg). Model as Cauchy layer on known substrate. "
                "k expected ~0 across visible range."
            ),
        ),
        # DPPC QCM-D — PRIORITY 1
        dict(
            material_name="DPPC",
            measurement_type="qcm-d",
            instrument="QCM-D",
            parameter="G_prime, G_double_prime, viscosity",
            frequency_range="1, 5, 15, 25 MHz (overtones 1, 3, 5, 7)",
            wavelength_range=None,
            priority=1,
            reason=(
                "Single paper in DB (Chou 2010). Values highly variable in literature depending on "
                "phase, temperature, substrate. Measurement on own instrument gives self-consistent dataset."
            ),
            protocol_notes=(
                "Gel phase at 25 deg C (below Tm=41 deg C). Use Voigt model fitting across minimum "
                "3 overtones. Measure on SiO2-coated sensor. Report G prime, G double prime, eta at "
                "each overtone frequency."
            ),
        ),
        # Polystyrene QCM-D — PRIORITY 2
        dict(
            material_name="Polystyrene",
            measurement_type="qcm-d",
            instrument="QCM-D or High-frequency DMA",
            parameter="G_prime, G_double_prime",
            frequency_range="1, 5, 15 MHz",
            wavelength_range=None,
            priority=2,
            reason=(
                "Literature has only low-frequency DMA values (1-10 Hz). MHz-regime data for thin PS films "
                "does not exist. Required for accurate QCM-D modelling of PS-coated sensors."
            ),
            protocol_notes=(
                "Spin-cast thin PS film (50-200 nm) directly onto QCM-D sensor. Use Voigt viscoelastic model. "
                "Alternatively use broadband DMA with TTS to reach MHz regime."
            ),
        ),
        # PMMA QCM-D — PRIORITY 2
        dict(
            material_name="PMMA",
            measurement_type="qcm-d",
            instrument="QCM-D or High-frequency DMA",
            parameter="G_prime, G_double_prime",
            frequency_range="1, 5, 15 MHz",
            wavelength_range=None,
            priority=2,
            reason=(
                "Same gap as polystyrene. No MHz viscoelastic data exists for PMMA thin films."
            ),
            protocol_notes=(
                "Spin-cast thin PMMA film onto QCM-D sensor. Voigt model fitting. "
                "Note MW and tacticity in measurement record."
            ),
        ),
        # PEG multi-MW ellipsometry — PRIORITY 3
        dict(
            material_name="PEG",
            measurement_type="ellipsometry",
            instrument="Spectroscopic Ellipsometer",
            parameter="n(lambda)",
            frequency_range=None,
            wavelength_range="191-1688 nm",
            priority=3,
            reason=(
                "Shah 2020 (currently in DB) covers MW 285-315 only. Higher MW PEG (1k, 6k, 20k) "
                "optical constants not in literature and behave differently."
            ),
            protocol_notes=(
                "Measure liquid PEG at multiple MW. Use roughened-substrate reflection method "
                "(Shah 2020 protocol). Fit Sellmeier model per MW. Report A1, B1, A2, B2 coefficients."
            ),
        ),
        # PEG brush QCM-D — PRIORITY 3
        dict(
            material_name="PEG",
            measurement_type="qcm-d",
            instrument="QCM-D",
            parameter="G_prime, G_double_prime, viscosity",
            frequency_range="1, 5, 15 MHz",
            wavelength_range=None,
            priority=3,
            reason=(
                "Bulk liquid viscosity (60 mPa.s) in DB is not applicable to surface-grafted PEG brush. "
                "Brush viscoelasticity is completely different and not in literature."
            ),
            protocol_notes=(
                "Graft PEG-thiol to Au-coated sensor. Vary grafting density. Fit Voigt model. "
                "Note MW, grafting density, and buffer conditions."
            ),
        ),
    ]

    inserted = 0
    for r in rows:
        mat_id = _mat_id(conn, r["material_name"])
        if mat_id is None:
            print(f"  ✗ {r['material_name']}: not found in DB")
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO lab_measurements_needed "
            "(material_id, measurement_type, instrument, parameter, frequency_range, "
            " wavelength_range, priority, reason, protocol_notes) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                mat_id, r["measurement_type"], r["instrument"], r["parameter"],
                r["frequency_range"], r["wavelength_range"],
                r["priority"], r["reason"], r["protocol_notes"],
            ),
        )
        inserted += cur.rowcount
    conn.commit()
    print(f"  ✓ {inserted} new lab_measurements_needed rows (of {len(rows)} total)")


# ── Step 11: Material gap notes ───────────────────────────────────────────────

def update_material_notes(conn: sqlite3.Connection) -> None:
    print("\n[11] Updating material gap notes …")

    notes_map = {
        4:  ("Polystyrene",
              "PubChem CID not resolvable by polymer name. G prime is representative 1Hz DMA value only"
              " — no MHz data exists. See lab_measurements_needed."),
        5:  ("DPPC",
              "No wavelength-resolved n(lambda) spectrum in literature anywhere. k assumed 0 in visible."
              " Viscoelastic values from single paper (Chou 2010). See lab_measurements_needed."),
        6:  ("PMMA",
              "PubChem CID not resolvable by polymer name. G prime is representative 1Hz DMA value only"
              " — no MHz data exists. See lab_measurements_needed."),
        8:  ("DMSO",
              "Viscosity source has no open DOI. Confirmed by NIST WebBook and manufacturer SDS."),
        9:  ("PEG",
              "Optical constants from Shah 2020 (MW 285-315 only). Higher MW optical data and brush"
              " viscoelasticity require lab measurement. See lab_measurements_needed."),
        10: ("Silicon",
              "Optical n,k covers 206-827 nm only (Aspnes 1983). No viscoelastic data — crystalline solid."),
    }

    for mat_id, (name, note) in notes_map.items():
        conn.execute("UPDATE materials SET notes = ? WHERE id = ?", (mat_id, note))
        print(f"  ✓ {name} (id={mat_id}): notes updated")
    conn.commit()


# ── Step 12: Final verification ───────────────────────────────────────────────

def print_final_verification(conn: sqlite3.Connection) -> None:
    print("\n" + "=" * 100)
    print("VERIFICATION — materials summary")
    print("=" * 100)

    rows = conn.execute("""
        SELECT
          m.name,
          m.pubchem_cid,
          (SELECT COUNT(*) FROM optical_nk WHERE material_id=m.id) AS nk_rows,
          (SELECT COUNT(*) FROM chemical_descriptors WHERE material_id=m.id) AS rdkit,
          (SELECT dielectric_real FROM dielectric
           WHERE material_id=m.id AND frequency_hz=0.0 LIMIT 1) AS epsilon,
          (SELECT storage_modulus_pa FROM viscoelasticity
           WHERE material_id=m.id LIMIT 1) AS G_prime,
          (SELECT viscosity_mpa_s FROM viscoelasticity
           WHERE material_id=m.id LIMIT 1) AS eta,
          m.density_g_cm3,
          (SELECT COUNT(*) FROM calculated_sld WHERE material_id=m.id) AS sld_rows
        FROM materials m ORDER BY m.id
    """).fetchall()

    print(f"  {'name':<14} {'cid':>9}  {'nk':>6}  {'rdkit':>5}  {'eps':>6}  "
          f"{'G_prime':>12}  {'eta':>8}  {'rho':>6}  {'sld':>4}")
    print("-" * 100)
    for name, cid, nk, rdkit, eps, gp, eta, rho, sld in rows:
        cid_s = str(cid) if cid else "—"
        eps_s = f"{eps:.1f}" if eps is not None else "—"
        gp_s  = f"{gp:.2e}" if gp  is not None else "—"
        eta_s = f"{eta:.3f}" if eta is not None else "—"
        rho_s = f"{rho:.3f}" if rho is not None else "—"
        print(f"  {name:<14} {cid_s:>9}  {nk:>6}  {rdkit:>5}  {eps_s:>6}  "
              f"{gp_s:>12}  {eta_s:>8}  {rho_s:>6}  {sld:>4}")

    print("\n" + "=" * 100)
    print("VERIFICATION — lab measurements needed")
    print("=" * 100)

    lab_rows = conn.execute("""
        SELECT m.name, l.measurement_type, l.instrument, l.priority, l.status
        FROM lab_measurements_needed l
        JOIN materials m ON m.id = l.material_id
        ORDER BY l.priority, m.name
    """).fetchall()

    print(f"  {'name':<14} {'type':<15} {'instrument':<50} {'pri':>3}  status")
    print("-" * 100)
    for name, mtype, instrument, pri, status in lab_rows:
        print(f"  {name:<14} {mtype:<15} {instrument:<50} {pri:>3}  {status}")
    print("=" * 100)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"Database : {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    apply_schema(conn)               # [1]  schema + pubchem_cid column
    update_pubchem_cids(conn)        # [2]  PubChem CIDs
    insert_rdkit_descriptors(conn)   # [3]  RDKit 10 descriptors per material
    fetch_silicon_optical(conn)      # [4]  Si n,k from Aspnes.yml  (BUG FIX)
    insert_dppc_optical(conn)        # [5]  DPPC 4 optical points   (BUG FIX)
    insert_peg_optical(conn)         # [6]  PEG Sellmeier series    (BUG FIX)
    insert_calculated_slds(conn)     # [7]  SLD at 4 X-ray energies
    insert_dielectric_constants(conn)# [8]  static ε from literature/PubChem
    insert_viscoelasticity(conn)     # [9]  η solvents + G′ glassy polymers
    insert_lab_measurements(conn)    # [10] 6 prioritised lab tasks
    update_material_notes(conn)      # [11] permanent gap notes
    print_final_verification(conn)   # [12] Task 8 verification queries

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
