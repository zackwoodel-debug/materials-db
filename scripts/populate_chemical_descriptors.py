"""
Populate chemical_descriptors for materials_normalized.db.

Priority per material:
  1. RDKit from SMILES already in materials table
  2. PubChem API (by pubchem_cid, then by name) → obtain SMILES → RDKit
  3. Legacy migration from legacy_chemical_descriptors (partial fill, no FP)
  4. Record in descriptor_failures
"""

import json
import math
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np

with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message=".*MorganGenerator.*")
    from rdkit import Chem
    from rdkit.Chem import AllChem, Descriptors, rdMolDescriptors

DB_PATH = Path(__file__).parent.parent / "data" / "materials_normalized.db"
REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
PUBCHEM_PROPS = (
    "MolecularFormula,MolecularWeight,ExactMass,"
    "IsomericSMILES,XLogP,TPSA,"
    "HBondDonorCount,HBondAcceptorCount,"
    "RotatableBondCount,HeavyAtomCount"
)
PUBCHEM_DELAY = 0.25  # seconds between requests (PubChem asks ≤5 req/s)

# Map legacy descriptor_name → chemical_descriptors column
LEGACY_NAME_MAP = {
    "ExactMolWt": "exact_mass",
    "exact_mass": "exact_mass",
    "TPSA": "tpsa",
    "MolLogP": "logp",
    "logP": "logp",
    "NumHeavyAtoms": "heavy_atom_count",
    "NumRotatableBonds": "rotatable_bonds",
    "rotatable_bonds": "rotatable_bonds",
    "NumHDonors": "hbond_donors",
    "h_bond_donors": "hbond_donors",
    "NumHAcceptors": "hbond_acceptors",
    "h_bond_acceptors": "hbond_acceptors",
    "NumAromaticRings": "aromatic_rings",
}


# ---------------------------------------------------------------------------
# RDKit helpers
# ---------------------------------------------------------------------------

def rdkit_descriptors(smiles: str) -> dict | None:
    """Compute all target descriptors from SMILES. Returns None if invalid."""
    if not smiles or not smiles.strip():
        return None
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*MorganGenerator.*")
        mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*MorganGenerator.*")
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius=2, nBits=2048)
    return {
        "exact_mass": round(Descriptors.ExactMolWt(mol), 6),
        "tpsa": round(Descriptors.TPSA(mol), 4),
        "logp": round(Descriptors.MolLogP(mol), 4),
        "heavy_atom_count": mol.GetNumHeavyAtoms(),
        "rotatable_bonds": int(rdMolDescriptors.CalcNumRotatableBonds(mol)),
        "hbond_donors": int(rdMolDescriptors.CalcNumHBD(mol)),
        "hbond_acceptors": int(rdMolDescriptors.CalcNumHBA(mol)),
        "aromatic_rings": int(rdMolDescriptors.CalcNumAromaticRings(mol)),
        "morgan_fp": fp.ToBitString(),
        "source": "rdkit",
    }


# ---------------------------------------------------------------------------
# PubChem helpers
# ---------------------------------------------------------------------------

def _pubchem_get(url: str) -> dict | None:
    time.sleep(PUBCHEM_DELAY)
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        props = data["PropertyTable"]["Properties"][0]
        return {
            "smiles": props.get("IsomericSMILES"),
            "molecular_weight": float(props["MolecularWeight"]) if "MolecularWeight" in props else None,
            "exact_mass": float(props["ExactMass"]) if "ExactMass" in props else None,
            "tpsa": float(props["TPSA"]) if "TPSA" in props else None,
            "logp": float(props["XLogP"]) if "XLogP" in props else None,
            "hbond_donors": int(props["HBondDonorCount"]) if "HBondDonorCount" in props else None,
            "hbond_acceptors": int(props["HBondAcceptorCount"]) if "HBondAcceptorCount" in props else None,
            "rotatable_bonds": int(props["RotatableBondCount"]) if "RotatableBondCount" in props else None,
            "heavy_atom_count": int(props["HeavyAtomCount"]) if "HeavyAtomCount" in props else None,
            "cid": props.get("CID"),
            "formula": props.get("MolecularFormula"),
        }
    except (KeyError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError):
        return None


def pubchem_by_cid(cid: int) -> dict | None:
    url = (
        f"{PUBCHEM_BASE}/compound/cid/{cid}"
        f"/property/{PUBCHEM_PROPS}/JSON"
    )
    return _pubchem_get(url)


def pubchem_by_name(name: str) -> dict | None:
    encoded = urllib.parse.quote(name)
    url = (
        f"{PUBCHEM_BASE}/compound/name/{encoded}"
        f"/property/{PUBCHEM_PROPS}/JSON"
    )
    return _pubchem_get(url)


# ---------------------------------------------------------------------------
# Legacy migration helper
# ---------------------------------------------------------------------------

def migrate_from_legacy(legacy_rows: list[dict]) -> dict:
    """
    Convert legacy_chemical_descriptors rows into chemical_descriptors columns.
    Uses LEGACY_NAME_MAP; ignores unmapped descriptor names.
    Returns partial dict (no morgan_fp).
    """
    result = {}
    for row in legacy_rows:
        col = LEGACY_NAME_MAP.get(row["descriptor_name"])
        if col and col not in result and row["value"] is not None:
            val = row["value"]
            if col in ("heavy_atom_count", "rotatable_bonds", "hbond_donors",
                       "hbond_acceptors", "aromatic_rings"):
                result[col] = int(round(val))
            else:
                result[col] = float(val)
    if result:
        result["source"] = "legacy_migration"
    return result


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def ensure_descriptor_failures_table(con: sqlite3.Connection):
    con.execute("DROP TABLE IF EXISTS descriptor_failures")
    con.execute("""
        CREATE TABLE descriptor_failures (
            failure_id       INTEGER PRIMARY KEY,
            material_id      INTEGER NOT NULL,
            material_name    TEXT    NOT NULL,
            smiles_available INTEGER NOT NULL DEFAULT 0,
            attempted_rdkit  INTEGER NOT NULL DEFAULT 0,
            attempted_pubchem INTEGER NOT NULL DEFAULT 0,
            attempted_legacy INTEGER NOT NULL DEFAULT 0,
            partial_fill     INTEGER NOT NULL DEFAULT 0,
            missing_fields   TEXT,
            reason           TEXT,
            created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    con.commit()


def load_legacy_descriptors(con: sqlite3.Connection) -> dict[int, list[dict]]:
    rows = con.execute(
        "SELECT material_id, descriptor_name, value, source_library "
        "FROM legacy_chemical_descriptors"
    ).fetchall()
    by_mat: dict[int, list[dict]] = {}
    for mid, dname, val, src in rows:
        by_mat.setdefault(mid, []).append(
            {"descriptor_name": dname, "value": val, "source_library": src}
        )
    return by_mat


TARGET_FIELDS = [
    "exact_mass", "tpsa", "logp", "heavy_atom_count",
    "rotatable_bonds", "hbond_donors", "hbond_acceptors",
    "aromatic_rings",
]


def missing_fields(desc: dict) -> list[str]:
    return [f for f in TARGET_FIELDS if desc.get(f) is None]


# ---------------------------------------------------------------------------
# Main population logic
# ---------------------------------------------------------------------------

def process_material(
    con: sqlite3.Connection,
    mat: dict,
    legacy_map: dict[int, list[dict]],
) -> tuple[dict | None, dict]:
    """
    Returns (descriptor_dict_or_None, failure_record).
    descriptor_dict has all required fields + source + morgan_fp.
    failure_record is always populated (partial_fill may be True).
    """
    mid = mat["material_id"]
    name = mat["name"]
    smiles = mat["smiles"]
    cid = mat["pubchem_cid"]

    attempted_rdkit = False
    attempted_pubchem = False
    attempted_legacy = False
    desc: dict = {}
    reasons: list[str] = []
    updated_smiles: str | None = None

    # --- Step 1: RDKit from existing SMILES ---
    if smiles:
        attempted_rdkit = True
        result = rdkit_descriptors(smiles)
        if result:
            desc = result
        else:
            reasons.append(f"RDKit could not parse SMILES: {smiles!r}")

    # --- Step 2: PubChem lookup (if no SMILES or RDKit failed) ---
    if not desc:
        attempted_pubchem = True
        pc = None
        if cid:
            pc = pubchem_by_cid(int(cid))
        if pc is None:
            pc = pubchem_by_name(name)

        if pc:
            pc_smiles = pc.get("smiles")
            if pc_smiles:
                # Update materials table with discovered SMILES
                updated_smiles = pc_smiles
                rdkit_result = rdkit_descriptors(pc_smiles)
                if rdkit_result:
                    # Merge RDKit result with any PubChem-only fields
                    desc = rdkit_result
                    # PubChem TPSA is more widely trusted for XLogP
                    if pc.get("tpsa") is not None:
                        desc["tpsa_pubchem"] = pc["tpsa"]
                    if pc.get("logp") is not None:
                        desc["logp_pubchem"] = pc["logp"]
                    reasons.append(f"SMILES resolved via PubChem CID={pc.get('cid')}")
                else:
                    # PubChem SMILES not parseable by RDKit — use PubChem values directly
                    desc = {k: pc[k] for k in TARGET_FIELDS if pc.get(k) is not None}
                    desc["source"] = "pubchem_only"
                    reasons.append(
                        f"PubChem SMILES not RDKit-parseable; using PubChem numeric values"
                    )
            else:
                # PubChem found the compound but no SMILES — use numeric values directly
                desc = {k: pc[k] for k in TARGET_FIELDS if pc.get(k) is not None}
                if desc:
                    desc["source"] = "pubchem_only"
                reasons.append("PubChem found compound but no SMILES available")
        else:
            reasons.append("PubChem lookup returned nothing")

    # --- Step 3: Legacy migration (fill remaining gaps) ---
    legacy_rows = legacy_map.get(mid, [])
    if legacy_rows:
        attempted_legacy = True
        legacy = migrate_from_legacy(legacy_rows)
        if not desc:
            desc = legacy
        else:
            # Only fill genuinely missing fields from legacy
            for field in TARGET_FIELDS:
                if desc.get(field) is None and legacy.get(field) is not None:
                    desc[field] = legacy[field]

    # --- Evaluate result ---
    missing = missing_fields(desc)
    partial = bool(desc) and bool(missing)
    full = bool(desc) and not missing

    failure_rec = {
        "material_id": mid,
        "material_name": name,
        "smiles_available": 1 if smiles else 0,
        "attempted_rdkit": int(attempted_rdkit),
        "attempted_pubchem": int(attempted_pubchem),
        "attempted_legacy": int(attempted_legacy),
        "partial_fill": int(partial),
        "missing_fields": json.dumps(missing) if missing else "[]",
        "reason": "; ".join(reasons) if reasons else "ok",
    }

    if desc:
        # Build descriptor_json with full provenance
        descriptor_json = {
            k: desc[k]
            for k in list(TARGET_FIELDS) + ["source", "tpsa_pubchem", "logp_pubchem"]
            if k in desc
        }
        descriptor_json["computed_at"] = datetime.now().isoformat()
        desc["descriptor_json"] = json.dumps(descriptor_json)
        if updated_smiles:
            desc["_updated_smiles"] = updated_smiles
        return desc, failure_rec

    return None, failure_rec


def write_descriptors(con: sqlite3.Connection, mid: int, desc: dict):
    # Update materials.smiles if we discovered one
    updated_smiles = desc.pop("_updated_smiles", None)
    if updated_smiles:
        current = con.execute(
            "SELECT smiles FROM materials WHERE material_id=?", (mid,)
        ).fetchone()
        if current and not current[0]:
            con.execute(
                "UPDATE materials SET smiles=? WHERE material_id=?",
                (updated_smiles, mid),
            )

    con.execute(
        """
        INSERT OR REPLACE INTO chemical_descriptors
          (material_id, exact_mass, tpsa, logp,
           heavy_atom_count, rotatable_bonds,
           hbond_donors, hbond_acceptors,
           aromatic_rings, descriptor_json, morgan_fp)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            mid,
            desc.get("exact_mass"),
            desc.get("tpsa"),
            desc.get("logp"),
            desc.get("heavy_atom_count"),
            desc.get("rotatable_bonds"),
            desc.get("hbond_donors"),
            desc.get("hbond_acceptors"),
            desc.get("aromatic_rings"),
            desc.get("descriptor_json"),
            desc.get("morgan_fp"),
        ),
    )


def write_failure(con: sqlite3.Connection, rec: dict):
    con.execute(
        """
        INSERT INTO descriptor_failures
          (material_id, material_name, smiles_available,
           attempted_rdkit, attempted_pubchem, attempted_legacy,
           partial_fill, missing_fields, reason)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            rec["material_id"], rec["material_name"],
            rec["smiles_available"], rec["attempted_rdkit"],
            rec["attempted_pubchem"], rec["attempted_legacy"],
            rec["partial_fill"], rec["missing_fields"], rec["reason"],
        ),
    )


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_reports(con: sqlite3.Connection):
    mats = con.execute(
        "SELECT material_id, name FROM materials ORDER BY material_id"
    ).fetchall()
    mat_name = {mid: name for mid, name in mats}

    cd_rows = con.execute(
        "SELECT cd.material_id, cd.exact_mass, cd.tpsa, cd.logp, "
        "cd.heavy_atom_count, cd.rotatable_bonds, cd.hbond_donors, "
        "cd.hbond_acceptors, cd.aromatic_rings, "
        "(CASE WHEN cd.morgan_fp IS NOT NULL THEN 1 ELSE 0 END) as has_fp, "
        "cd.descriptor_json "
        "FROM chemical_descriptors cd ORDER BY cd.material_id"
    ).fetchall()

    fail_rows = con.execute(
        "SELECT material_id, material_name, smiles_available, "
        "attempted_rdkit, attempted_pubchem, attempted_legacy, "
        "partial_fill, missing_fields, reason "
        "FROM descriptor_failures ORDER BY material_id"
    ).fetchall()

    total_mat = len(mats)
    populated = len(cd_rows)
    full = sum(
        1 for r in cd_rows
        if all(r[i] is not None for i in range(1, 9))
    )
    partial = populated - full
    failures = sum(1 for f in fail_rows if f[6] == 0 and f[7] != "ok")

    # --- property_population_report.md ---
    lines = [
        "# Descriptor Population Report",
        f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total materials | {total_mat} |",
        f"| Descriptors populated (any) | {populated} |",
        f"| Fully populated (all 8 fields) | {full} |",
        f"| Partially populated | {partial} |",
        f"| No descriptors | {total_mat - populated} |",
        f"| With Morgan fingerprint | {sum(1 for r in cd_rows if r[9])} |",
        "",
        "## Per-Material Descriptor Coverage",
        "",
        "| material_id | Name | exact_mass | tpsa | logp | heavy_atom_count"
        " | rotatable_bonds | hbond_donors | hbond_acceptors | aromatic_rings | Morgan FP | Source |",
        "|-------------|------|-----------|------|------|-----------------|"
        "-----------------|-------------|-----------------|----------------|-----------|--------|",
    ]
    for r in cd_rows:
        (mid, exact_mass, tpsa, logp, hac, rb, hbd, hba, ar, has_fp, djson) = r
        src = "—"
        if djson:
            try:
                src = json.loads(djson).get("source", "—")
            except Exception:
                pass

        def fmt(v):
            if v is None:
                return "—"
            if isinstance(v, float):
                return f"{v:.4g}"
            return str(v)

        lines.append(
            f"| {mid} | {mat_name.get(mid, '?')} "
            f"| {fmt(exact_mass)} | {fmt(tpsa)} | {fmt(logp)} "
            f"| {fmt(hac)} | {fmt(rb)} | {fmt(hbd)} | {fmt(hba)} "
            f"| {fmt(ar)} | {'✓' if has_fp else '—'} | {src} |"
        )

    lines += [
        "",
        "## Failures & Partial Fills",
        "",
        "| material_id | Name | Partial | Missing Fields | Reason |",
        "|-------------|------|---------|----------------|--------|",
    ]
    for f in fail_rows:
        (mid, mname, sma, ardkit, apc, aleg, pfill, mfields, reason) = f
        missing_str = ", ".join(json.loads(mfields)) if mfields and mfields != "[]" else "none"
        lines.append(
            f"| {mid} | {mname} | {'yes' if pfill else 'no'} "
            f"| {missing_str} | {reason} |"
        )

    lines += [""]
    (REPORTS_DIR / "descriptor_population_report.md").write_text("\n".join(lines) + "\n")

    # --- unresolved_materials.csv ---
    unresolved = con.execute(
        """
        SELECT m.material_id, m.name, m.formula, m.smiles, m.pubchem_cid,
               df.missing_fields, df.reason
        FROM materials m
        LEFT JOIN chemical_descriptors cd ON cd.material_id = m.material_id
        LEFT JOIN descriptor_failures df ON df.material_id = m.material_id
        WHERE cd.material_id IS NULL
           OR (df.partial_fill = 1)
        ORDER BY m.material_id
        """
    ).fetchall()
    unresolved_lines = ["material_id,name,formula,smiles,pubchem_cid,missing_fields,reason"]
    for r in unresolved:
        mid, name, formula, smiles, cid, mf, reason = r
        row_vals = [
            str(mid or ""), _csv_escape(name or ""), _csv_escape(formula or ""),
            _csv_escape(smiles or ""), str(cid or ""),
            _csv_escape(mf or ""), _csv_escape(reason or ""),
        ]
        unresolved_lines.append(",".join(row_vals))
    (REPORTS_DIR / "unresolved_materials.csv").write_text("\n".join(unresolved_lines) + "\n")

    # --- descriptor_failures.csv ---
    fail_lines = [
        "material_id,material_name,smiles_available,attempted_rdkit,"
        "attempted_pubchem,attempted_legacy,partial_fill,missing_fields,reason"
    ]
    for f in fail_rows:
        (mid, mname, sma, ardkit, apc, aleg, pfill, mfields, reason) = f
        row_vals = [
            str(mid), _csv_escape(mname), str(sma), str(ardkit),
            str(apc), str(aleg), str(pfill),
            _csv_escape(mfields or ""), _csv_escape(reason or ""),
        ]
        fail_lines.append(",".join(row_vals))
    (REPORTS_DIR / "descriptor_failures.csv").write_text("\n".join(fail_lines) + "\n")

    print(f"  Wrote reports/descriptor_population_report.md")
    print(f"  Wrote reports/unresolved_materials.csv  ({len(unresolved)} rows)")
    print(f"  Wrote reports/descriptor_failures.csv   ({len(fail_rows)} rows)")


def _csv_escape(v: str) -> str:
    if "," in v or '"' in v or "\n" in v:
        return '"' + v.replace('"', '""') + '"'
    return v


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    print(f"Connecting to {DB_PATH}")
    con = sqlite3.connect(DB_PATH)

    print("Setting up descriptor_failures table...")
    ensure_descriptor_failures_table(con)

    print("Loading legacy descriptor data...")
    legacy_map = load_legacy_descriptors(con)
    print(f"  {sum(len(v) for v in legacy_map.values())} legacy rows for "
          f"{len(legacy_map)} materials")

    materials = con.execute(
        "SELECT material_id, name, formula, smiles, inchikey, "
        "molecular_weight, cas_number, pubchem_cid FROM materials ORDER BY material_id"
    ).fetchall()
    col_names = ["material_id", "name", "formula", "smiles", "inchikey",
                 "molecular_weight", "cas_number", "pubchem_cid"]
    materials = [dict(zip(col_names, row)) for row in materials]

    results = {"full": 0, "partial": 0, "none": 0}
    print(f"\nProcessing {len(materials)} materials...")

    for mat in materials:
        mid = mat["material_id"]
        name = mat["name"]
        print(f"  [{mid:2d}] {name:<20}", end=" ")

        desc, failure_rec = process_material(con, mat, legacy_map)

        if desc:
            write_descriptors(con, mid, desc)
            missing = missing_fields(desc)
            if missing:
                results["partial"] += 1
                print(f"partial  (missing: {missing})")
            else:
                results["full"] += 1
                src = desc.get("source", "?")
                print(f"full     [source: {src}]")
        else:
            results["none"] += 1
            print(f"FAILED   ({failure_rec['reason']})")

        write_failure(con, failure_rec)

    con.commit()

    print(f"\n  Full:    {results['full']}")
    print(f"  Partial: {results['partial']}")
    print(f"  None:    {results['none']}")

    print("\nGenerating reports...")
    generate_reports(con)

    con.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
