"""Descriptors v2 (scripts/release_descriptors.py, scripts/fetch_mp_structure_extras.py), each checked by an independent route:
valence electrons = Z - Z(noble-gas core) from periodictable; ionization energies / affinities against NIST values; Crippen
molar refractivity against the Lorentz-Lorenz molar refraction of the release's own measured n and density; the local-structure
numbers recomputed from the cached structures; oxidation-state guesses kept out of the ML features."""
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import generate_ml_release_set as ml  # noqa: E402
import release_descriptors as rd  # noqa: E402

EXTRAS = json.loads(rd.MP_EXTRAS.read_text())
NOBLE = [0, 2, 10, 18, 36, 54, 86, 118]


def test_valence_electrons_are_the_electrons_outside_the_noble_gas_core():
    import periodictable as pt
    from pymatgen.core import Element
    for z in range(1, 95):
        el = Element.from_Z(z)
        core = max(n for n in NOBLE if n < z) if z not in NOBLE else max(n for n in NOBLE if n < z)
        assert rd.valence_electrons(el) == z - core, el.symbol
        assert sum(rd.valence_electrons(el, o) for o in "spdf") == rd.valence_electrons(el)
        assert pt.elements[z].number == z
    from pymatgen.core import Element as E
    assert [rd.valence_electrons(E("Pb"), o) for o in "spdf"] == [2, 2, 10, 14]


@pytest.mark.parametrize("formula,prop,expected,tol", [
    ("Si", "first_ionization_energy", 8.15168, 1e-3), ("NaCl", "first_ionization_energy", (5.13908 + 12.96764) / 2, 1e-3),
    ("Cl", "electron_affinity", 3.612725, 1e-3), ("O", "first_ionization_energy", 13.61805, 1e-3),  # NIST ASD
    ("GaAs", "valence_electrons", (13 + 15) / 2, 1e-9), ("GaAs", "valence_d_electrons", 10, 1e-9),
])
def test_element_property_statistics(formula, prop, expected, tol):
    assert rd.compositional(formula)[prop]["mean"] == pytest.approx(expected, abs=tol)


def test_block_fractions_sum_to_one():
    for f in ["TiO2", "Bi4Ge3O12", "Er2O3", "C8H8", "NaCl", "Au"]:
        b = rd.compositional(f)["block_fractions"]
        assert sum(b.values()) == pytest.approx(1.0) and set(b) == set("spdf")
    assert rd.compositional("Er2O3")["block_fractions"]["f"] == pytest.approx(0.4)


def test_crippen_molar_refractivity_agrees_with_lorentz_lorenz_from_measured_n_and_density():
    """R = (n^2-1)/(n^2+2) * M / rho from the release's own measurements vs Crippen MR from structure alone (v0.15.0: 39 liquids,
    r 0.9992, median 0.9%, worst 4.7% styrene). A liquid far off would mean a wrong n, density or SMILES."""
    from rdkit import Chem
    from rdkit.Chem import Descriptors
    fm = pytest.importorskip("pandas").read_parquet(ROOT / "data" / "ML_release_feature_matrix.parquet")
    from materials_db.access import AccessError, find_release
    try:
        _, db = find_release()  # the newest release by version number (material ids are permanent from v0.13.0)
    except AccessError:
        pytest.skip("no release built locally")
    smi = dict(sqlite3.connect(db).execute("SELECT material_id, smiles FROM materials"))
    pairs = []
    for r in fm[(fm.meta_material_kind == "molecule") & fm.target_n_633nm.notna() & fm.target_density_g_cm3.notna()].itertuples():
        s = smi.get(r.material_id)
        if s:
            n, rho, m = r.target_n_633nm, r.target_density_g_cm3, Descriptors.MolWt(Chem.MolFromSmiles(s))
            pairs.append(((n * n - 1) / (n * n + 2) * m / rho, rd.molecular_extended(s)["molar_refractivity_crippen"]))
    ll, mr = np.array(pairs).T
    rel_err = np.abs(mr / ll - 1)
    assert len(pairs) >= 35 and np.corrcoef(ll, mr)[0, 1] > 0.995 and np.median(rel_err) < 0.02 and rel_err.max() < 0.06


def test_repeat_unit_attachment_points_add_nothing():
    ps = rd.molecular_extended("*CC(*)c1ccccc1")
    assert ps["molar_refractivity_crippen"] == pytest.approx(33.99, abs=0.01) and ps["valence_electrons"] == 40  # C8H8


def test_chemistry_block():
    nacl = rd.chemistry("NaCl")
    assert nacl["oxidation_state_guess"] == {"Cl": -1.0, "Na": 1.0} and nacl["n_oxidation_state_guesses"] == 1
    assert nacl["pauling_ionic_character"] == pytest.approx(1 - math.exp(-(3.16 - 0.93) ** 2 / 4), abs=1e-6)
    gst = rd.chemistry("Ge2Sb2Te5")
    assert gst["n_oxidation_state_guesses"] > 1 and "other assignments also balance" in gst["oxidation_state_note"]


def test_oxidation_guesses_are_not_ml_features():
    src = Path(ml.__file__).read_text()
    assert "oxidation" not in src and "chemistry" not in src


def test_extras_cache_is_consistent_with_the_structural_cache():
    base = json.loads(rd.MP_CACHE.read_text())
    assert EXTRAS["mp_database_version"] == base["mp_database_version"] and EXTRAS["volume_drift_vs_base_cache"] == []
    assert set(EXTRAS["entries"]) == set(base["entries"]) and EXTRAS["missing"] == []


def test_local_environment_recomputes_from_the_cached_structures():
    from pymatgen.core import Structure
    import fetch_mp_structure_extras as fx
    rng = np.random.default_rng(0)
    ids = sorted(EXTRAS["entries"])
    for mid in list(rng.choice(ids, 12, replace=False)) + ["mp-22862", "mp-149", "mp-66"]:  # + NaCl, Si, diamond
        e = EXTRAS["entries"][mid]
        again = fx.local_environment(Structure.from_dict(e["structure"]))
        for k in ("coordination_number_mean", "bond_length_mean_angstrom", "packing_fraction"):
            if k in e:
                assert again[k] == pytest.approx(e[k], rel=1e-6), (mid, k)
    assert EXTRAS["entries"]["mp-22862"]["coordination_number_mean"] == 6 and EXTRAS["entries"]["mp-149"]["coordination_number_mean"] == 4


def test_elastic_moduli_are_physical():
    n = 0
    for mid, e in EXTRAS["entries"].items():
        el = e["elastic"]
        if "unavailable" in el:
            continue
        n += 1
        k, g, nu = el["bulk_modulus_vrh_gpa"], el["shear_modulus_vrh_gpa"], el["poisson_ratio"]
        if k is not None and g is not None and k > 0 and g > 0 and nu is not None:
            assert nu == pytest.approx((3 * k - 2 * g) / (2 * (3 * k + g)), abs=0.02), mid  # isotropic relation (VRH)
    assert n >= 150
