#!/usr/bin/env python3
"""
scripts/xrr_smoke_test_oxide_db.py
====================================
Model-fit connection smoke test requested at CHECKPOINT 3 review: point the
XRR simulator at data/materials_oxide_test.db and run
"Vacuum,TiO2:50,SiO2:100,Silicon", selecting layers by material + dataset_label.

The existing src/materials_db/calculators/{simulate_xrr,xrr_engine}.py cannot
do this unmodified -- see the findings printed at the end. This script reuses
the schema-agnostic Parratt recursion (parratt()) from simulate_xrr.py but
reads density/SLD itself, directly from physical_properties by
(material formula, dataset_label), which is the actual new schema shape.
"""

import sqlite3
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))

from materials_db.calculators.simulate_xrr import parratt  # noqa: E402

DB_PATH = _ROOT / "data" / "materials_oxide_test.db"

# elemental Si has no row in materials_oxide_test.db (an oxides-only dataset)
# -- standard crystalline Si substrate values, computed independently for
# this smoke test only, NOT read from either DB.
SI_SUBSTRATE_DENSITY = 2.329  # g/cm3
SI_SUBSTRATE_XRAY_SLD = None  # filled in via periodictable below


def read_layer_by_dataset_label(conn, formula: str, dataset_label_prefix: str) -> dict:
    """The real lookup our new schema requires: material + dataset_label,
    not just a bare material name. physical_properties rows for a given
    material/polymorph are split by quantity (density vs xray_sld_real vs
    xray_sld_imag vs neutron_sld_*), all sharing the same dataset_label
    polymorph prefix -- see data/CHECKPOINT_2_report.md / CHECKPOINT_3 notes.
    """
    mat_row = conn.execute("SELECT material_id, name FROM materials WHERE formula = ?", (formula,)).fetchone()
    if mat_row is None:
        raise ValueError(f"No materials row for formula={formula}")
    material_id, name = mat_row

    def get_value(column, label_suffix):
        row = conn.execute(
            f"SELECT {column} FROM physical_properties "
            f"WHERE material_id = ? AND dataset_label = ?",
            (material_id, f"{dataset_label_prefix} | {label_suffix}"),
        ).fetchone()
        return row[0] if row else None

    density_row = conn.execute(
        "SELECT density_g_cm3, dataset_label FROM physical_properties "
        "WHERE material_id = ? AND density_g_cm3 IS NOT NULL",
        (material_id,),
    ).fetchone()
    density = density_row[0] if density_row else None
    density_label = density_row[1] if density_row else None

    xray_real = get_value("xray_sld", "xray_sld_real | periodictable_CuKalpha")
    xray_imag = get_value("xray_sld", "xray_sld_imag | periodictable_CuKalpha")

    return dict(name=name, formula=formula, material_id=material_id,
                density_g_cm3=density, density_label=density_label,
                xray_sld_real=xray_real, xray_sld_imag=xray_imag)


def main():
    conn = sqlite3.connect(str(DB_PATH))

    tio2 = read_layer_by_dataset_label(conn, "TiO2", "rutile")
    sio2 = read_layer_by_dataset_label(conn, "SiO2", "amorphous")
    conn.close()

    print("=== Layers read from materials_oxide_test.db by (formula, dataset_label) ===")
    for layer in (tio2, sio2):
        print(f"  {layer['name']} ({layer['formula']}): density={layer['density_g_cm3']:.4f} g/cm3, "
              f"xray_sld=({layer['xray_sld_real']:.4f} + {layer['xray_sld_imag']:.6f}j) x1e-6 A^-2")

    import periodictable
    si = periodictable.formula("Si", density=SI_SUBSTRATE_DENSITY)
    si_real, si_imag = si.xray_sld(energy=8.048)
    print(f"\n  Silicon (substrate, NOT in materials_oxide_test.db -- standard crystalline Si used instead): "
          f"density={SI_SUBSTRATE_DENSITY} g/cm3, xray_sld=({si_real:.4f} + {si_imag:.6f}j) x1e-6 A^-2")

    # Parratt SLD convention: units of 1e-6 A^-2 -> A^-2
    slds = np.array([
        0.0,                                   # Vacuum
        (tio2["xray_sld_real"]) * 1e-6,        # TiO2, 50 A
        (sio2["xray_sld_real"]) * 1e-6,        # SiO2, 100 A
        float(si_real) * 1e-6,                 # Silicon substrate
    ])
    thicknesses = np.array([0.0, 50.0, 100.0, 0.0])

    q_arr = np.linspace(0.005, 0.5, 1000)
    R = parratt(q_arr, slds, thicknesses)

    print(f"\n=== Parratt simulation, q = 0.005-0.5 A^-1 (1000 points) ===")
    print(f"R at q=0.005 (should be ~1, TER plateau): {R[0]:.6f}")
    print(f"R at q=0.5   (should be small, high-Q decay): {R[-1]:.4e}")

    # Critical q for the substrate (total external reflection cutoff)
    qc_substrate = np.sqrt(16 * np.pi * slds[-1])
    print(f"Estimated substrate critical q_c = sqrt(16*pi*SLD_Si) = {qc_substrate:.5f} A^-1")

    below_qc = R[q_arr < qc_substrate * 0.8]
    above_high_q = R[q_arr > 0.3]
    print(f"Mean R well below q_c ({(q_arr < qc_substrate*0.8).sum()} points): {below_qc.mean():.6f}")
    print(f"Mean R at high q>0.3 ({(q_arr > 0.3).sum()} points): {above_high_q.mean():.4e}")

    # Fresnel-like power-law decay check: log(R) vs log(q) slope should be
    # close to -4 well above the critical edge and any thickness fringes.
    mask = q_arr > 0.35
    slope = np.polyfit(np.log(q_arr[mask]), np.log(R[mask]), 1)[0]
    print(f"log-log decay slope for q>0.35 (Fresnel ~ -4 expected): {slope:.2f}")

    out_path = _ROOT / "data" / "xrr_oxide_smoke_test_output.csv"
    with open(out_path, "w") as f:
        f.write("q_invA,R\n")
        for q, r in zip(q_arr, R):
            f.write(f"{q:.6f},{r:.8e}\n")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
