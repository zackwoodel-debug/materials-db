"""scripts/package_ml_dataset.py: the ML package. Splits round-trip exactly, the Croissant file describes every column and file with
the right checksums, the card's configs name the real files, the build is deterministic, and it stops on mismatched inputs."""
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import package_ml_dataset as pk  # noqa: E402


@pytest.fixture(scope="module")
def pkg(tmp_path_factory):
    root = tmp_path_factory.mktemp("pkg")
    out, zpath, counts = pk.build(root)
    return out, zpath, counts, root


def read_split(out, table):
    return pd.concat([pd.read_parquet(out / table / f"{s}.parquet") for s in pk.SPLIT_NAMES], ignore_index=True)


def test_tables_round_trip_with_their_splits(pkg):
    out, *_ = pkg
    feats = read_split(out, "materials").sort_values("material_id").reset_index(drop=True)
    orig = pd.read_parquet(pk.FEATURES).sort_values("material_id").reset_index(drop=True)
    pd.testing.assert_frame_equal(feats[orig.columns], orig)
    splits = pd.read_csv(pk.SPLITS).set_index("material_id")
    assert (feats.set_index("material_id").split == splits.split).all()
    spec = read_split(out, "spectra")
    assert len(spec) == len(pd.read_parquet(pk.SPECTRA))
    assert (spec.split == spec.material_id.map(splits.split)).all()
    for s in pk.SPLIT_NAMES:
        assert set(pd.read_parquet(out / "spectra" / f"{s}.parquet").split) == {s}


def test_croissant_covers_every_file_and_column(pkg):
    out, *_ = pkg
    cr = json.loads((out / "croissant.json").read_text())
    objs = {d["contentUrl"]: d["sha256"] for d in cr["distribution"] if d["@type"] == "cr:FileObject"}
    for rel, digest in objs.items():
        assert hashlib.sha256((out / rel).read_bytes()).hexdigest() == digest
    for rs in cr["recordSet"]:
        cols = list(pd.read_parquet(out / rs["name"] / "train.parquet").columns)
        assert [f["name"] for f in rs["field"]] == cols
        assert all(f["description"] for f in rs["field"])
    arrays = [f["name"] for rs in cr["recordSet"] for f in rs["field"] if f.get("isArray")]
    assert sorted(arrays) == ["k", "k_mask", "n", "n_mask"]
    assert cr["datePublished"] and cr["license"].endswith("/by/4.0/")


def test_card_configs_point_at_real_files(pkg):
    out, *_ = pkg
    text = (out / "README.md").read_text()
    head = text.split("---")[1]
    paths = [ln.split("path:")[1].strip() for ln in head.splitlines() if "path:" in ln]
    assert len(paths) == 6 and all((out / p).exists() for p in paths)
    assert "license: cc-by-4.0" in head


def test_checksums_zip_and_determinism(pkg, tmp_path):
    out, zpath, _, root = pkg
    sums = dict(reversed(ln.split("  ")) for ln in (out / "SHA256SUMS").read_text().splitlines())
    assert "croissant.json" in sums and "materials/train.parquet" in sums
    for rel, digest in sums.items():
        assert hashlib.sha256((out / rel).read_bytes()).hexdigest() == digest
    out2, zpath2, *_ = pk.build(tmp_path)
    assert (out2 / "SHA256SUMS").read_text() == (out / "SHA256SUMS").read_text()
    assert zpath2.read_bytes() == zpath.read_bytes()


def test_root_citation_is_current(pkg):
    version = json.loads(pk.METADATA["features"].read_text())["source_release"]
    assert (ROOT / "CITATION.cff").read_text() == pk.citation(version)


def test_zenodo_metadata(pkg):
    out, *_ = pkg
    z = json.loads((out / ".zenodo.json").read_text())
    assert z["upload_type"] == "dataset" and z["license"] == "cc-by-4.0" and z["creators"]


def test_stops_on_mismatched_releases(monkeypatch, tmp_path):
    meta = json.loads(pk.METADATA["splits"].read_text())
    meta["source_release"] = "0.0.1"
    fake = tmp_path / "splits_metadata.json"
    fake.write_text(json.dumps(meta))
    monkeypatch.setitem(pk.METADATA, "splits", fake)
    with pytest.raises(pk.PackageError):
        pk.build(tmp_path)


def test_every_materials_column_is_described():
    for c in pd.read_parquet(pk.FEATURES).columns:
        assert pk.describe(c, "materials")
    with pytest.raises(pk.PackageError):
        pk.describe("mystery_column", "materials")
