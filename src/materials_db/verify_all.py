#!/usr/bin/env python3
"""End-to-end verification: DB init, CSV parse, Parratt simulation.

Exit 0 on success; non-zero with printed failure message otherwise.
"""

import io
import sys

import numpy as np

from src.db.schema import init_db, insert_material, insert_optical, insert_mechanical
from src.pipeline.parser import parse_csv
from materials_db.simulation.xrr import parratt

# ---------------------------------------------------------------------------
# Physical constants for SLD derivation (NIST / CODATA)
# ---------------------------------------------------------------------------
_NA  = 6.02214076e23   # Avogadro (mol⁻¹)
_R_E = 2.8179403e-5    # classical electron radius (Å)


def _xsld(rho_g_cm3: float, mw_g_mol: float, z_total: int) -> float:
    """X-ray SLD in Å⁻² from bulk density, molecular weight, electron count."""
    rho_e = (rho_g_cm3 * _NA * z_total) / (mw_g_mol * 1e24)  # e⁻/Å³
    return float(rho_e * _R_E)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, condition: bool, msg: str = "") -> None:
    if condition:
        _passed.append(name)
    else:
        _failed.append(f"{name}: {msg}" if msg else name)


# ---------------------------------------------------------------------------
# 1. DB initialisation and round-trip insert/query
# ---------------------------------------------------------------------------

conn = init_db(":memory:")

mat_id = insert_material(conn, "DPPC", "Fluid/Method4")
insert_optical(conn, mat_id, "Fluid/Method4", 670.0, 1.3829)
insert_optical(conn, mat_id, "Fluid/Method4", 785.0, 1.3792)
insert_mechanical(conn, mat_id, "PBS-filled", 1.000, 5700.0, 204517.0, 2.17)

row = conn.execute(
    "SELECT wavelength_nm, n FROM optical_constants WHERE material_id=? ORDER BY wavelength_nm",
    (mat_id,),
).fetchall()

check("db_init",       conn is not None)
check("db_optical_n",  len(row) == 2, f"expected 2 optical rows, got {len(row)}")
check("db_n_670",      abs(row[0][1] - 1.3829) < 1e-9, f"n@670={row[0][1]}")
check("db_n_785",      abs(row[1][1] - 1.3792) < 1e-9, f"n@785={row[1][1]}")

mrow = conn.execute(
    "SELECT shear_storage_pascal, shear_loss_pascal FROM mechanical_qcmd WHERE material_id=?",
    (mat_id,),
).fetchone()
check("db_shear_storage", mrow is not None and mrow[0] == 5700.0,   f"got {mrow}")
check("db_shear_loss",    mrow is not None and mrow[1] == 204517.0, f"got {mrow}")

# ---------------------------------------------------------------------------
# 2. CSV parse — present and missing columns
# ---------------------------------------------------------------------------

complete_csv = io.StringIO(
    "wavelength_nm,n,k\n"
    "633.0,1.46,0.0\n"
    "785.0,1.45,0.0\n"
)
df = parse_csv(complete_csv)
check("csv_columns",  {"wavelength_nm", "n", "k"}.issubset(df.columns))
check("csv_rows",     len(df) == 2, f"expected 2 rows, got {len(df)}")
check("csv_n_val",    abs(df["n"].iloc[0] - 1.46) < 1e-9)

incomplete_csv = io.StringIO("wavelength_nm,n\n633.0,1.46\n")
df2 = parse_csv(incomplete_csv, required_columns=["wavelength_nm", "n", "k"])
check("csv_missing_k_added", "k" in df2.columns, "k column not backfilled")
check("csv_missing_k_nan",   bool(df2["k"].isna().all()), f"k={df2['k'].tolist()}")

# ---------------------------------------------------------------------------
# 3. Parratt simulation — vacuum / SiO2 (20 Å) / Si substrate
#
#   Si:   rho=2.329 g/cm³, Mw=28.085 g/mol, Z=14  → SLD≈1.97e-5 Å⁻²
#   SiO2: rho=2.196 g/cm³, Mw=60.085 g/mol, Z=30  → SLD≈1.86e-5 Å⁻²
#   (densities: NIST SRD 69; values are established references, not invented)
# ---------------------------------------------------------------------------

sld_Si   = _xsld(2.329, 28.085, 14)
sld_SiO2 = _xsld(2.196, 60.085, 30)

Q   = np.linspace(0.01, 0.60, 500)
sld = np.array([0.0, sld_SiO2, sld_Si])
d   = np.array([0.0,     20.0,     0.0])   # Å
sig = np.array([3.0,      3.0,     3.0])   # Å RMS roughness

R = parratt(Q, sld, d, sig)

check("R_length", len(R) == len(Q), f"len(R)={len(R)}, expected {len(Q)}")
check(
    "R_bounds",
    bool(np.all((R >= 0.0) & (R <= 1.0))),
    f"R out of [0,1]: min={R.min():.6f}, max={R.max():.6f}",
)
# Physical sanity: TER plateau should give R=1 well below the critical edge
q_c_approx = np.sqrt(16.0 * np.pi * sld_Si)   # ≈ 0.031 Å⁻¹
plateau_mask = Q < 0.8 * q_c_approx
check(
    "R_TER_plateau",
    bool(np.all(R[plateau_mask] > 0.999)),
    f"TER not flat below 0.8·q_c: min R={R[plateau_mask].min():.6f}",
)
# High-Q tail should be small
check(
    "R_highQ_decay",
    bool(R[Q > 0.4].max() < 0.01),
    f"high-Q R too large: {R[Q > 0.4].max():.4f}",
)

# ---------------------------------------------------------------------------
# 4. Energy Converter and SLD Calculations Verification
# ---------------------------------------------------------------------------
from materials_db.calculators.sld_calculator import EnergyConverter, compute_xray_sld, compute_neutron_sld, parse_formula

# Energy converter tests
wl_test = 0.15406  # nm (Cu K-alpha)
energy_test = EnergyConverter.wl_to_energy(wl_test)
check("energy_conv_wl_to_E", abs(energy_test - 8047.786) < 0.1)
check("energy_conv_E_to_wl", abs(EnergyConverter.energy_to_wl(energy_test) - wl_test) < 1e-9)

# SLD computations verification
# PMMA formula repeating unit: C5H8O2, density 1.19 g/cm3, Mw 100.1158 g/mol, Z=54
counts_pmma = parse_formula("C5H8O2")
xray_pmma = compute_xray_sld(counts_pmma, 1.19, 100.1158)
neutron_pmma = compute_neutron_sld(counts_pmma, 1.19, 100.1158)
check("sld_pmma_xray", abs(xray_pmma.real - 1.0892e-5) < 1e-7)
check("sld_pmma_neutron", abs(neutron_pmma - 1.067e-6) < 1e-8)

# Deuterated material check
counts_dpmma = parse_formula("C5D8O2")
neutron_dpmma = compute_neutron_sld(counts_dpmma, 1.28, 108.16)
check("sld_dpmma_neutron", abs(neutron_dpmma - 6.999e-6) < 1e-7)

# ---------------------------------------------------------------------------
# 5. Database v2 schema verification
# ---------------------------------------------------------------------------
ref_id = conn.execute(
    "INSERT INTO references_db (doi, citation_text) VALUES (?, ?)",
    ("10.1062/test", "Test Citation 2026")
).lastrowid
check("db_insert_reference", ref_id is not None)

conn.execute(
    "INSERT INTO chemical_descriptors (material_id, descriptor_name, value, source_library) VALUES (?, ?, ?, ?)",
    (mat_id, "logP", 1.45, "RDKit")
)
desc_val = conn.execute(
    "SELECT value FROM chemical_descriptors WHERE material_id=? AND descriptor_name=?",
    (mat_id, "logP")
).fetchone()[0]
check("db_insert_descriptor", abs(desc_val - 1.45) < 1e-9)

conn.execute(
    "INSERT INTO dielectrics (material_id, reference_id, frequency_hz, temperature_C, real_permittivity) VALUES (?, ?, ?, ?, ?)",
    (mat_id, ref_id, 1000.0, 25.0, 2.5)
)
diel_val = conn.execute(
    "SELECT real_permittivity FROM dielectrics WHERE material_id=? AND frequency_hz=?",
    (mat_id, 1000.0)
).fetchone()[0]
check("db_insert_dielectric", abs(diel_val - 2.5) < 1e-9)

conn.execute(
    "INSERT INTO calculated_slds (material_id, reference_id, energy_ev, wavelength_nm, xray_sld_real, neutron_sld_real) VALUES (?, ?, ?, ?, ?, ?)",
    (mat_id, ref_id, 8040.0, 0.154, 1.08e-5, 1.06e-6)
)
sld_val = conn.execute(
    "SELECT xray_sld_real, neutron_sld_real FROM calculated_slds WHERE material_id=? AND energy_ev=?",
    (mat_id, 8040.0)
).fetchone()
check("db_insert_calculated_sld_xray", abs(sld_val[0] - 1.08e-5) < 1e-9)
check("db_insert_calculated_sld_neutron", abs(sld_val[1] - 1.06e-6) < 1e-9)

# ---------------------------------------------------------------------------
# 6. Integration test — real init path, on-disk DB, SQLAgent, views
# ---------------------------------------------------------------------------
import os
import sqlite3 as _sqlite3
import tempfile
from pathlib import Path as _Path

from materials_db.init_db import run_sql_file as _run_sql_file
from materials_db.core.sql_agent import SQLAgent as _SQLAgent

_proj_root = _Path(__file__).resolve().parent

_tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tf_path = _tf.name
_tf.close()
try:
    _run_sql_file(_Path(_tf_path), _proj_root / "core" / "schema.sql")
    _run_sql_file(_Path(_tf_path), _proj_root / "core" / "seed_manual.sql")

    _ic = _sqlite3.connect(_tf_path)
    _ic.execute(
        "INSERT OR IGNORE INTO materials "
        "(name, formula, material_class, notes, density_g_cm3) "
        "VALUES ('IntTestMat', 'H2O', 'solvent', 'integration test row', 1.0)"
    )
    _mid = _ic.execute(
        "SELECT id FROM materials WHERE name='IntTestMat'"
    ).fetchone()[0]
    _ic.execute(
        "INSERT OR IGNORE INTO optical_nk (material_id, wavelength_nm, n) "
        "VALUES (?, 633.0, 1.33)",
        (_mid,),
    )
    _ic.commit()
    _ic.close()

    _agent = _SQLAgent(_tf_path)

    _vc = _sqlite3.connect(_tf_path)
    _views = {r[0] for r in _vc.execute(
        "SELECT name FROM sqlite_master WHERE type='view'"
    ).fetchall()}
    check("integration_materials_flat_exists", "materials_flat" in _views,
          f"views found: {_views}")
    check("integration_spr_data_exists", "spr_data" in _views,
          f"views found: {_views}")

    _mf_rows = _vc.execute("SELECT * FROM materials_flat").fetchall()
    check("integration_materials_flat_rows", len(_mf_rows) > 0,
          f"materials_flat returned {len(_mf_rows)} rows")

    _spr_rows = _vc.execute("SELECT * FROM spr_data").fetchall()
    check("integration_spr_data_rows", len(_spr_rows) > 0,
          f"spr_data returned {len(_spr_rows)} rows")

    _vc.close()
finally:
    os.unlink(_tf_path)

# ---------------------------------------------------------------------------
# 7. Stack pipeline checks
# ---------------------------------------------------------------------------

try:
    from materials_db.core.stack_schema import StackFile as _SF, _round_trip_check as _rtc
    from materials_db.pipeline.stack_exporter import build_stack as _build_stack
    from materials_db.pipeline.stack_to_sim import (
        simulate_stack_xrr as _sim_xrr,
        to_qcm_input as _qcm_in,
        to_voigt_params as _voigt,
    )
    import json as _json_mod

    _stacks_dir_v = _proj_root.parents[1] / "data" / "stacks"
    _mdb_path = _proj_root.parents[1] / "data" / "materials.db"

    # 7a. stack_schema_roundtrip — both example JSONs load, validate, and round-trip
    _RT_NAMES = ("pmma_gold_si.json", "dppc_bilayer_si.json")
    try:
        _missing = [n for n in _RT_NAMES if not (_stacks_dir_v / n).exists()]
        if _missing:
            check("stack_schema_roundtrip", False, f"missing: {_missing}")
        else:
            for _rname in _RT_NAMES:
                _rtc(_stacks_dir_v / _rname)
            check("stack_schema_roundtrip", True)
    except Exception as _exc:
        check("stack_schema_roundtrip", False, str(_exc))

    # 7b. stack_export_ps_gold — PS n within 0.01 of 1.5875, SLD within 5%, Gold G'==27e9
    if _mdb_path.exists():
        try:
            _sf_pg = _build_stack(
                [
                    {"material": "Polystyrene", "thickness": 1000.0},
                    {"material": "Gold", "thickness": 50.0},
                    {"material": "quartz", "substrate": True},
                ],
                sample_id="verify-ps-gold",
                user="verify_all",
                proposal_id="V-001",
                db_path=_mdb_path,
            )
            _ps_mol = _sf_pg.stack[1].molecular
            _gold_params = _voigt(_sf_pg.stack[2])
            check(
                "stack_export_ps_gold",
                (
                    _ps_mol is not None
                    and abs(_ps_mol.n_at_633nm - 1.5875) < 0.01
                    and _ps_mol.xray_sld_A2_CuKa is not None
                    and abs(_ps_mol.xray_sld_A2_CuKa / 9.58e-6 - 1.0) < 0.05
                    and _gold_params["modulus_storage"] is not None
                    and abs(_gold_params["modulus_storage"] - 27e9) < 1e6
                ),
                f"n={getattr(_ps_mol,'n_at_633nm',None)}, "
                f"sld={getattr(_ps_mol,'xray_sld_A2_CuKa',None)}, "
                f"G'={_gold_params.get('modulus_storage')}",
            )
        except Exception as _exc:
            check("stack_export_ps_gold", False, str(_exc))
    else:
        check("stack_export_ps_gold", False, f"DB not found: {_mdb_path}")

    # 7c. stack_physics_rejects — n=0.5 polymer triggers a violation
    try:
        from materials_db.core.stack_schema import Layer as _Layer, Molecular as _Mol
        _bad_sf = _SF(
            stack_id="bad-n",
            sample_id="reject-test",
            material="FakePolymer",
            n_layers=2,
            stack=[
                _Layer(label="Vacuum", role="ambient"),
                _Layer(
                    label="FakePolymer",
                    material_type="polymer",
                    molecular=_Mol(n_at_633nm=0.5),
                ),
            ],
        )
        _viol = _bad_sf.validate_physics()
        check(
            "stack_physics_rejects",
            any("n_at_633nm" in v for v in _viol),
            f"violations={_viol}",
        )
    except Exception as _exc:
        check("stack_physics_rejects", False, str(_exc))

    # 7d. stack_xrr_runs — TER plateau and high-Q decay on SiO2/Si inline stack
    try:
        from materials_db.core.stack_schema import (
            BoundedValue as _BV, Layer as _Lyr, Scattering as _Scat,
            StackFile as _SFX, Structural as _Str,
        )
        _sio2_si_sf = _SFX(
            stack_id="test-xrr",
            sample_id="SiO2-on-Si",
            material="SiO2",
            n_layers=3,
            stack=[
                _Lyr(label="Vacuum", material_type="vacuum", role="ambient",
                     scattering=_Scat(sld_real=0.0)),
                _Lyr(label="SiO2", material_type="oxide",
                     structural=_Str(thickness=_BV(value=20.0)),
                     scattering=_Scat(sld_real=sld_SiO2)),
                _Lyr(label="Silicon", material_type="semiconductor", role="substrate",
                     scattering=_Scat(sld_real=sld_Si)),
            ],
        )
        _Qv = np.linspace(0.01, 0.60, 500)
        _Rv = _sim_xrr(_sio2_si_sf, Q=_Qv)
        _qc_v = np.sqrt(16.0 * np.pi * sld_Si)
        _pm_v = _Qv < 0.8 * _qc_v
        check(
            "stack_xrr_runs",
            (
                len(_Rv) == len(_Qv)
                and bool(np.all(_Rv[_pm_v] > 0.999))
                and bool(_Rv[_Qv > 0.4].max() < 0.01)
            ),
            f"TER_min={_Rv[_pm_v].min():.4f}, highQ_max={_Rv[_Qv > 0.4].max():.4f}",
        )
    except Exception as _exc:
        check("stack_xrr_runs", False, str(_exc))

    # 7e. stack_qcm_mapping — substrate impedance == 8.8e6 for the QCM example
    if _mdb_path.exists():
        try:
            _qcm_out = _qcm_in(_sf_pg)  # reuse the PS/Gold/quartz stack from 7b
            check(
                "stack_qcm_mapping",
                _qcm_out["impedance"] is not None
                and abs(_qcm_out["impedance"] - 8.8e6) < 1.0,
                f"impedance={_qcm_out['impedance']}",
            )
        except Exception as _exc:
            check("stack_qcm_mapping", False, str(_exc))
    else:
        check("stack_qcm_mapping", False, f"DB not found: {_mdb_path}")

except ImportError as _imp_err:
    for _cn in (
        "stack_schema_roundtrip",
        "stack_export_ps_gold",
        "stack_physics_rejects",
        "stack_xrr_runs",
        "stack_qcm_mapping",
    ):
        check(_cn, False, f"import error: {_imp_err}")

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

for name in _passed:
    print(f"  PASS  {name}")
for msg in _failed:
    print(f"  FAIL  {msg}")

if _failed:
    print(f"\n{len(_failed)} check(s) failed.")
    sys.exit(1)

print(f"\nAll {len(_passed)} checks passed.")
sys.exit(0)
