"""scripts/dataset_kind.py: a page is a model fit only when its source says so explicitly."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dataset_kind import is_model_fit, model_fit_reason  # noqa: E402


@pytest.mark.parametrize("path", [
    "main/GaAs/nk/Adachi.yml",      # calculation script: Adachi's model dielectric function
    "main/GaAs/nk/Rakic.yml",       # "Modeling the optical dielectric function ... Extension of Adachi's model"
    "main/GaAs/nk/Ozaki.yml",       # "Fit of author's experimental data to a simplified model"
    "main/GaAs/nk/Franta-300K.yml",  # "Dispersion models describing coupled systems ..."
])
def test_model_fits(path):
    assert is_model_fit(path), path


@pytest.mark.parametrize("path", [
    "main/GaAs/nk/Aspnes.yml",      # ellipsometry
    "main/GaAs/nk/Skauli.yml",      # "Improved dispersion relations": a Sellmeier fit of measured n
    "main/SiO2/nk/Malitson.yml",    # the reference Sellmeier formula of measured fused silica
    "main/GaP/nk/Bond.yml",         # prism measurement
])
def test_measured(path):
    assert model_fit_reason(path) is None, path


def test_a_model_named_as_the_purpose_of_a_measurement_is_not_a_model_fit():
    import json
    sel = json.loads((Path(__file__).resolve().parents[1] / "data" / "step1_selections_liquids.json").read_text())
    myers = [a["data_path"] for v in sel.values() if v for a in v["axes"] if a["page"].startswith("Myers")]
    assert myers and not any(is_model_fit(p) for p in myers)  # "... measurement of n and k ... for optical modeling and detection"
