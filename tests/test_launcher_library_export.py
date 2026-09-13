"""Tests for src/materials_db/launcher/library_export.py: the
slab_model_builder.py "material library" JSON exporter -- a different,
complementary path from the CLI-driven stack launcher, letting ModalFit's
own native stack-BUILDER tool browse this whole catalog directly.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.launcher.library_export import (  # noqa: E402
    build_library_entry, build_material_library,
)
from materials_db.pipeline.process_condition import DENSITY_BULK_APPROXIMATION  # noqa: E402

_DB_PATH = ROOT / "data" / "materials_oxide_test.db"
pytestmark = pytest.mark.skipif(not _DB_PATH.exists(), reason="data/materials_oxide_test.db not built")


class TestBuildLibraryEntry:
    def test_verified_material_label_and_shape(self, tmp_path):
        entry = build_library_entry(str(_DB_PATH), "Hafnium dioxide", None, tmp_path)
        assert entry["name"] == "Hafnium dioxide"
        assert entry["label"] == "Hafnium dioxide (HfO2) -- verified"
        assert "BULK_APPROXIMATION" not in entry["label"]
        assert entry["material_type"] == "oxide"
        # optical.params.file must be ABSOLUTE (a library outlives any one
        # model's own directory -- see module docstring for why this
        # differs from export_stack()'s relative-path convention).
        assert Path(entry["optical"]["params"]["file"]).is_absolute()
        assert Path(entry["optical"]["params"]["file"]).exists()
        assert entry["scattering"]["sld_real"]["value"] > 0
        # no per-instance fields on a reusable material template
        assert "structural" not in entry
        assert "viscoelastic" not in entry

    def test_bulk_approximation_material_flagged_in_label(self, tmp_path):
        entry = build_library_entry(str(_DB_PATH), "Gold", None, tmp_path)
        assert "BULK_APPROXIMATION" in entry["label"]
        assert entry["molecular_descriptors"]["density_confidence"] == DENSITY_BULK_APPROXIMATION

    def test_molecular_descriptors_carries_citation_and_confidence(self, tmp_path):
        entry = build_library_entry(str(_DB_PATH), "Hafnium dioxide", None, tmp_path)
        md = entry["molecular_descriptors"]
        assert md["formula"] == "HfO2"
        assert "density_confidence" in md
        assert "density_bounds" in md
        assert "optical_source" in md  # citation passthrough

    def test_diamond_and_graphite_get_distinct_sidecar_files(self, tmp_path):
        """Same ambiguity _find_material() guards against elsewhere:
        confirms the library exporter doesn't collapse two materials
        sharing a formula into one file."""
        diamond = build_library_entry(str(_DB_PATH), "Diamond", "diamond cubic", tmp_path)
        graphite = build_library_entry(str(_DB_PATH), "Graphite", "graphite", tmp_path)
        d_file = diamond["optical"]["params"]["file"]
        g_file = graphite["optical"]["params"]["file"]
        assert d_file != g_file
        assert Path(d_file).exists() and Path(g_file).exists()


class TestBuildMaterialLibrary:
    def test_full_catalog_matches_known_distribution(self, tmp_path):
        library, errors = build_material_library(str(_DB_PATH), tmp_path)
        assert errors == []
        assert len(library["materials"]) == 133
        n_bulk = sum(1 for m in library["materials"] if "BULK_APPROXIMATION" in m["label"])
        assert n_bulk == 37
        assert len(library["materials"]) - n_bulk == 96

    def test_named_exclusions_are_not_in_the_library(self, tmp_path):
        library, _ = build_material_library(str(_DB_PATH), tmp_path)
        names = {m["name"] for m in library["materials"]}
        assert "Gadolinium(III) fluoride" not in names
        assert "Lutetium aluminium borate" not in names

    def test_every_sidecar_file_is_unique_and_present(self, tmp_path):
        """One CSV per material, no silent overwrite -- the same shape
        the Sapphire nk-filename bug was, checked here at library scale."""
        library, _ = build_material_library(str(_DB_PATH), tmp_path)
        files = [m["optical"]["params"]["file"] for m in library["materials"]
                 if m["optical"]["model"] == "Tabulated n,k"]
        assert len(files) == len(set(files))
        for f in files:
            assert Path(f).exists()
