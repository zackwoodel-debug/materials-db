#!/usr/bin/env python3
"""
scripts/dataset_kind.py
=======================
Is an RI.info page MEASURED data or a MODEL FIT of the dielectric function? Used by the family matchers' primary-dataset rule
(measured before model fits, then widest range).

A page counts as a model fit only when the source says so explicitly:
  * its REFERENCES carry RI.info's "Calculation script" link (the tabulated values were generated from a published model),
  * its COMMENTS say the data is a fit to a (simplified) model of the interband transitions, or
  * the referenced paper's title makes a model its subject: "Modeling the optical/dielectric ...", "<name>'s model", "Dispersion
    models describing ..." (Skauli's "Improved dispersion relations" and Myers' "measurement ... for optical modeling" are measured).
Sellmeier/Cauchy-type formula pages are MEASURED: they are the authors' representation of their measured n (e.g. Malitson's
fused silica), not a physical model of the dielectric function.
"""
import re
from functools import lru_cache
from pathlib import Path

import yaml

RI_DATA = Path(__file__).resolve().parents[1] / "refractiveindex_db" / "database" / "data"
# the paper's SUBJECT is a model ("Modeling the optical dielectric function ...", "Extension of Adachi's model", "Dispersion models
# describing ..."); a model as the PURPOSE of a measurement ("... measurement of n and k ... for optical modeling") does not count
_TITLE = re.compile(r"\bmodel(?:l)?ing the (?:optical|dielectric)\b|\b\w+['’]s model\b|\bdispersion models describing\b", re.I)
_COMMENT = re.compile(r"\bfit of [^.]*\bmodel\b|\bsimplified model\b", re.I)


def _strip(s):
    return re.sub(r"<[^>]+>", " ", str(s or ""))


@lru_cache(maxsize=None)
def model_fit_reason(data_path):
    """Why the page is a model fit (a short quote of the evidence), or None when it is measured data."""
    d = yaml.safe_load(open(RI_DATA / data_path))
    refs, comments = _strip(d.get("REFERENCES")), _strip(d.get("COMMENTS"))
    if "Calculation script" in refs:
        return "RI.info calculation script (values generated from a published model)"
    if m := _COMMENT.search(comments):
        return f"comment: '{m.group(0)}'"
    if m := _TITLE.search(refs):
        return f"reference title: '{m.group(0)}'"
    return None


def is_model_fit(data_path):
    return model_fit_reason(data_path) is not None
