"""v0.21.0 renamed six datasets' labels (structure:amorphous where the dataset's evidence states it; dropped where it does not)
and cleared "amorphous" from five polymorph slots. Old labels must keep resolving to the same data everywhere a label is looked
up, a wrong label must still raise, the stable registry keys and ids are unchanged, and no polymorph field holds a structure
state (except the one tracked exception)."""
import glob
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from materials_db.core import label_aliases  # noqa: E402
from materials_db.export.modalfit import ExportError, export_layer  # noqa: E402
from materials_db.pipeline.process_condition import is_structure_value  # noqa: E402

BASE = ROOT / "data" / "materials_oxide_test.db"
SIO2 = "Silicon dioxide (fused silica)"


def _con():
    return sqlite3.connect(f"file:{BASE}?mode=ro", uri=True)


def _labels(formula):
    return {label for (label,) in _con().execute(
        "SELECT DISTINCT o.dataset_label FROM optical_dispersion o JOIN materials m USING (material_id) WHERE m.formula = ?",
        (formula,))}


def test_every_alias_points_at_a_label_that_exists_and_the_old_one_is_gone():
    for (formula, old), new in label_aliases.OPTICAL.items():
        labels = _labels(formula)
        assert new in labels and old not in labels, (formula, old, new)


@pytest.mark.parametrize("label", [None, "amorphous", "amorphous | Malitson1965", "structure:amorphous | Malitson1965"])
def test_export_with_old_or_new_labels_gives_the_same_layer(tmp_path, label):
    reference = export_layer(_con(), SIO2, nk_csv_dir=tmp_path / "ref")
    layer = export_layer(_con(), SIO2, label, nk_csv_dir=tmp_path / "x")
    assert layer == reference
    assert layer["materials_db"]["optical_dataset_label"] == "structure:amorphous | Malitson1965"
    assert layer["materials_db"]["dataset_label"] == "density_literature"  # the density row asserts no structure


@pytest.mark.parametrize("name, old, new", [
    ("Germanium dioxide", "Fleming1984", "structure:amorphous | Fleming1984"),
    ("Niobium pentoxide", "amorphous | Franta2024", "Franta2024"),
    ("Silicon monoxide", "amorphous", "Hass1954"),
    ("Boron", "amorphous | FernandezPerea2007", "FernandezPerea2007"),
])
def test_other_relabelled_materials_export_through_their_old_labels(tmp_path, name, old, new):
    assert export_layer(_con(), name, old, nk_csv_dir=tmp_path)["materials_db"]["optical_dataset_label"] == new


@pytest.mark.parametrize("label", ["amorphous | Nope1999", "Malitson1966", "rutile"])
def test_a_wrong_label_still_raises(tmp_path, label):
    with pytest.raises(ExportError):
        export_layer(_con(), SIO2, label, nk_csv_dir=tmp_path)


def test_xrr_stack_syntax_with_the_old_label_reads_the_same_density():
    from materials_db.calculators.xrr_engine import read_material
    assert read_material(str(BASE), "SiO2", "amorphous") == read_material(str(BASE), "SiO2") == ("SiO2", 2.2)


def test_access_layer_resolves_old_labels_in_a_release_that_has_the_new_ones():
    from materials_db.access import AccessError, ReleaseDB
    try:
        db = ReleaseDB()
    except AccessError:
        pytest.skip("no release built locally")
    labels = set(db.datasets.dataset_label)
    if "structure:amorphous | Malitson1965" not in labels:
        pytest.skip("the newest local release predates v0.21.0")
    mid = int(db.materials.index[db.materials.name == SIO2][0])
    assert db._dataset(mid, "amorphous | Malitson1965").dataset_label == "structure:amorphous | Malitson1965"
    with pytest.raises(AccessError):
        db._dataset(mid, "amorphous | Nope1999")


def test_registry_keys_and_ids_are_unchanged_through_the_key_aliases():
    import build_release as br
    import material_registry as mreg
    reg = mreg.load()
    keys = mreg.keys_by_name(br.family_rows())
    for name, key, mid in [(SIO2, "oxides_50:SiO2@amorphous", 38), ("Boron", "batch3b_4:B@amorphous", 135),
                           ("Niobium pentoxide", "oxides_50:Nb2O5@amorphous", 33)]:
        assert keys[name] == key and reg["materials"][key]["id"] == mid


def test_a_key_alias_may_not_shadow_a_registered_key_or_point_nowhere():
    import material_registry as mreg
    reg = json.loads(json.dumps(mreg.load()))
    reg["key_aliases"] = {"oxides_50:TiO2@rutile": "oxides_50:SiO2@amorphous"}
    with pytest.raises(mreg.RegistryError):
        mreg.key_aliases(reg)
    reg["key_aliases"] = {"oxides_50:Xx": "oxides_50:Nothing"}
    with pytest.raises(mreg.RegistryError):
        mreg.key_aliases(reg)


KNOWN_EXCEPTIONS = {("batch2_31.csv", "Arsenic trisulfide")}  # tracked: as2s3_amorphous_in_polymorph


def test_no_polymorph_field_holds_a_structure_state():
    found = set()
    for path in sorted(glob.glob(str(ROOT / "data" / "*.csv"))):
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if "polymorph" in df.columns and "name" in df.columns:
            found |= {(Path(path).name, n) for n, p in zip(df["name"], df["polymorph"]) if is_structure_value(p)}
    assert found == KNOWN_EXCEPTIONS  # strict both ways: a new case fails, and so does fixing As2S3 without updating this


@pytest.mark.parametrize("value, expected", [("amorphous", True), ("Single crystal", True), ("poly-crystalline", False),
                                             ("polycrystalline", True), ("rutile", False), (None, False)])
def test_structure_vocabulary(value, expected):
    assert is_structure_value(value) is expected
