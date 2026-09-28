"""scripts/generate_ml_splits.py: grouped splits. No group straddles a split or fold, identical compositions and product lines
share a group, assignment depends only on the group id (stable across releases), and the committed CSV is current."""
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_ml_splits as gs  # noqa: E402

FEATURES = pd.read_parquet(gs.FEATURES)
SPLITS = pd.read_csv(gs.OUT_CSV)
META = json.loads(gs.OUT_METADATA.read_text())


def test_committed_splits_are_current():
    fresh = gs.assign(FEATURES)
    pd.testing.assert_frame_equal(fresh, SPLITS, check_dtype=False)
    assert META["source_release"] == json.loads(gs.FEATURE_META.read_text())["source_release"]


def test_every_material_once_and_no_group_straddles():
    assert SPLITS.material_id.is_unique and set(SPLITS.material_id) == set(FEATURES.material_id)
    assert SPLITS.groupby("group").split.nunique().eq(1).all()
    assert SPLITS.groupby("group").fold.nunique().eq(1).all()
    assert set(SPLITS.split) == {"train", "validation", "test"} and set(SPLITS.fold) == set(range(gs.N_FOLDS))


def test_identical_compositions_share_a_group():
    frac = [c for c in FEATURES.columns if c.startswith("feat_frac_")]
    comp = FEATURES[frac].round(4).fillna(0)
    has = comp.sum(axis=1) > 0
    sig = comp[has].apply(tuple, axis=1)
    grp = SPLITS.set_index("material_id").loc[FEATURES.loc[has, "material_id"], "group"].to_numpy()
    assert pd.Series(grp, index=sig.index).groupby(sig.to_numpy()).nunique().eq(1).all()


@pytest.mark.parametrize("keys", [("polymers:PMMA-Tomson", "polymers:PMMA-Mitsubishi", "polymers:PMMA-950-resist"),
                                  ("batch3b_4:C@graphite", "batch3b_4:C@diamond cubic"),
                                  ("liquids:1-C3H7OH", "liquids:2-C3H7OH"), ("liquids:H2O", "liquids:D2O"),
                                  ("gases:C2H4", "polymers:PE-HDPE"),
                                  tuple(gs.PRODUCT_LINES["cargille-matching-liquids"]), tuple(gs.PRODUCT_LINES["silk-fibroin"])])
def test_known_near_duplicates_are_together(keys):
    assert SPLITS.set_index("meta_key").loc[list(keys), "group"].nunique() == 1


def test_assignment_depends_only_on_the_group_id():
    """Dropping materials (a smaller or different release) never moves the others -- except a series member whose anchor end
    member was dropped (its group is the anchor's; without it, series:<name>): tested by the series tests below."""
    sub = gs.assign(FEATURES.sample(frac=0.5, random_state=1), strict=False).set_index("material_id")
    sub = sub[~sub.meta_family.isin(gs.SERIES_FAMILIES)]
    full = SPLITS.set_index("material_id").loc[sub.index]
    assert (sub.split == full.split).all() and (sub.fold == full.fold).all()


def test_product_line_rules():
    bad = FEATURES.assign(meta_key=FEATURES.meta_key.replace({"optical_media:Cargille-BK7": "optical_media:Cargille-BK7-renamed"}))
    with pytest.raises(gs.SplitError):
        gs.assign(bad)  # a product-line key that no longer exists
    lines = dict(gs.PRODUCT_LINES, water=["liquids:H2O"])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(gs, "PRODUCT_LINES", lines)
        with pytest.raises(gs.SplitError):
            gs.assign(FEATURES)  # a material with a composition cannot be put in a product line


def test_sizes_near_nominal_and_metadata_consistent():
    n = len(SPLITS)
    frac = SPLITS.split.value_counts() / n
    assert 0.7 < frac["train"] < 0.9 and 0.05 < frac["validation"] < 0.15 and 0.05 < frac["test"] < 0.15
    assert {s: v["materials"] for s, v in META["per_split"].items()} == SPLITS.split.value_counts().to_dict()
    assert META["groups"] == SPLITS.group.nunique()


def test_spectra_rows_inherit_their_material_split():
    spec = pd.read_parquet(ROOT / "data" / "ML_release_spectra.parquet", columns=["material_id"])
    assert set(spec.material_id) <= set(SPLITS.material_id)


def test_series_members_join_their_anchor_group():
    """A composition series (alloys, perovskites) shares the group of its first end member in the release, else series:<name>."""
    ends = gs.series_end_members()
    group_of = dict(zip(SPLITS.meta_key, SPLITS.group))
    for key, grp in group_of.items():
        if key.split(":", 1)[0] in gs.SERIES_FAMILIES:
            series = key.split(":", 1)[1].split("@")[0]
            anchor = next((group_of[e] for e in ends[series] if e in group_of), None)
            assert grp == (anchor or f"series:{series}"), key


def test_series_never_move_an_existing_material():
    """The series rule only places series members: every other material's group is what it would be without any series."""
    without = gs.assign(FEATURES[~FEATURES.meta_family.isin(gs.SERIES_FAMILIES)], strict=False).set_index("material_id")
    full = SPLITS.set_index("material_id").loc[without.index]
    assert (without.group == full.group).all() and (without.split == full.split).all()
