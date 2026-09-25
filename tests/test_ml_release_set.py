"""Tests for the release ML set (scripts/generate_ml_release_set.py -> data/ML_release_feature_matrix.parquet).

The committed parquet is checked on its own (no leakage, no fabricated values, fingerprints only for molecules). When the
release it was built from is present locally, it is also regenerated and compared cell by cell, and its targets are
recomputed by an independent route (the family tables' own n_633, the release's density rows).
"""
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_ml_release_set as ml  # noqa: E402

DF = pd.read_parquet(ml.OUT_PARQUET)
META = json.loads(ml.OUT_METADATA.read_text())
RELEASE = ROOT / "release" / f"materials-db-v{META['source_release']}"
FP = [c for c in DF if c.startswith("feat_fp_")]
FRAC = [c for c in DF if c.startswith("feat_frac_")]
needs_release = pytest.mark.skipif(not RELEASE.exists(), reason=f"{RELEASE.name} not built locally")


def test_one_row_per_material():
    assert len(DF) == META["n_materials"]
    assert DF["material_id"].is_unique and DF["meta_name"].is_unique


def test_no_target_is_a_feature():
    feats = META["feature_columns"] + META["element_fraction_columns"] + META["fp_columns"]
    assert not set(feats) & set(META["target_columns"])
    assert not [c for c in feats if "633" in c or "density" in c]  # incl. MP's DFT density, the MP_DFT density target


def test_metadata_lists_every_column():
    listed = set(META["feature_columns"] + META["element_fraction_columns"] + META["fp_columns"] + META["target_columns"])
    assert listed == {c for c in DF if c.startswith(("feat_", "target_"))}
    assert META["target_present"] == {c: int(DF[c].notna().sum()) for c in META["target_columns"]}
    assert META["scaled"] is False


def test_fingerprint_only_for_molecules():
    mol, rest = DF[DF.has_molecular], DF[~DF.has_molecular]
    assert rest[FP].isna().all().all() and rest[[c for c in DF if c.startswith("feat_mol_")]].isna().all().all()
    assert set(np.unique(mol[FP].to_numpy())) <= {0.0, 1.0}
    assert (mol[FP].sum(axis=1) > 0).all()
    assert (DF.loc[DF.meta_material_kind.str.contains("inorganic", na=False), "has_molecular"] == False).all()  # noqa: E712


def test_composition_blocks():
    comp = DF[DF.has_composition]
    assert ((comp[FRAC].sum(axis=1) - 1).abs() < 1e-5).all()  # release stores fractions to 6 decimals
    assert DF.loc[~DF.has_composition, FRAC].isna().all().all()  # unknown composition stays unknown, not 0
    struct_cols = [c for c in DF if c.startswith("feat_struct_")]
    assert DF.loc[~DF.has_structure, struct_cols].isna().all().all()
    assert (DF.loc[DF.has_structure, [c for c in struct_cols if c.startswith("feat_struct_system_")]].sum(axis=1) == 1).all()


def test_targets_physical_and_inside_measured_range():
    n = DF.dropna(subset=["target_n_633nm"])
    assert (n.target_n_633nm > 0).all()
    assert ((n.meta_primary_wl_min_nm <= 633) & (n.meta_primary_wl_max_nm >= 633)).all()  # never extrapolated
    k = DF.dropna(subset=["target_k_633nm"])
    assert (k.loc[k.target_k_633nm < 0, "meta_primary_has_negative_k"]).all()  # only ever the source's own value
    assert set(DF.loc[DF.meta_primary_has_negative_k, "meta_name"]) == {  # Querry's far-IR tails and Sarkar's resist fit
        "Copper(I) oxide", "Hematite", "Micro resist ma-N 1407 (negative resist)"}
    d = DF.dropna(subset=["target_density_g_cm3"])
    assert d.target_density_g_cm3.between(0.05, 25).all() and d.meta_density_kind.notna().all()
    assert DF.loc[DF.target_density_g_cm3.isna(), "meta_density_kind"].isna().all()


def test_known_values():
    at = DF.set_index("meta_name")
    assert at.at["Gold", "target_n_633nm"] == pytest.approx(0.18, abs=0.02)   # Johnson & Christy
    assert at.at["Gold", "target_k_633nm"] == pytest.approx(3.43, abs=0.05)
    assert at.at["Silicon", "target_n_633nm"] == pytest.approx(3.88, abs=0.02)  # Aspnes
    assert at.at["Water", "target_n_633nm"] == pytest.approx(1.332, abs=0.002)
    assert at.at["Chrysoberyl", "meta_primary_dataset"].endswith("Walling-alpha.yml")  # "Walling-α" on the page


@needs_release
def test_regenerates_identically():
    df, _ = ml.build(RELEASE)
    pd.testing.assert_frame_equal(df.reset_index(drop=True), DF.reset_index(drop=True), check_dtype=False)


@needs_release
def test_targets_match_release_independently():
    assert ml.check(DF, RELEASE) < 0.01  # vs the family tables' n_633 (exact formula evaluation where the page has one)
    con = sqlite3.connect(str(next(RELEASE.glob("*.sqlite"))))
    dens = dict(con.execute("SELECT m.name, p.density_g_cm3 FROM physical_properties p JOIN materials m USING(material_id) "
                            "WHERE p.density_g_cm3 IS NOT NULL").fetchall())
    ours = DF.set_index("meta_name").target_density_g_cm3.dropna().to_dict()
    assert set(ours) == set(dens) and all(math.isclose(ours[k], dens[k]) for k in ours)
    prim = dict(con.execute("SELECT m.name, COUNT(DISTINCT o.raw_record_table) FROM optical_dispersion o "
                            "JOIN materials m USING(material_id) GROUP BY m.name").fetchall())
    assert DF.set_index("meta_name").meta_n_optical_datasets.to_dict() == prim
