"""Phase 3 recorded evidence and decisions only (docs/phase3-evidence-and-couplings.md): the oxide gaps entries and the tracked tasks
exist and agree with each other, and every quoted piece of evidence appears verbatim in the file it is attributed to. Nothing here
asserts anything about polymorph, selection_key, dataset labels or database contents: those are unchanged by Phase 3.
"""
import ast
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.pipeline.process_condition import open_tasks, task_detail  # noqa: E402

GAPS = pd.read_csv(ROOT / "data" / "oxide_gaps.csv")
RI = ROOT / "refractiveindex_db" / "database"
DOC = (ROOT / "docs" / "phase3-evidence-and-couplings.md").read_text()

EXPECTED = {  # (stable key, gap_kind) -> phase3 case
    ("oxides_50:Nb2O5@amorphous", "structure_unresolved"): "D (blocked)",
    ("oxides_50:SiO@amorphous", "structure_unresolved"): "B",
    ("oxides_50:SiO2@amorphous", "density_provenance"): "blocked",
    ("oxides_50:GeO2", "density_provenance"): "blocked",
    ("oxides_50:Ta2O5@amorphous", "density_provenance"): "blocked",
    ("oxides_50:SiO@amorphous", "density_provenance"): "blocked",
    ("oxides_50:Nb2O5@amorphous", "density_provenance"): "blocked",
    ("oxides_50:SiO2@amorphous", "identity_conflict"): "deferred (tracked task material38_identity_correction)",
}


def test_oxide_gaps_hold_exactly_the_recorded_entries():
    got = {(k, g): c for k, g, c in GAPS[["key", "gap_kind", "phase3_case"]].values}
    assert got == EXPECTED
    assert GAPS["reason"].notna().all() and GAPS["evidence"].notna().all()
    assert GAPS["source_lookup_2026_09_30"].notna().all()  # each entry records what the 2026-09-30 literature lookup found
    # only excluded_page rows are consumed by other builders (glass catalogs); these entries must not exclude anything
    assert "excluded_page" not in set(GAPS["gap_kind"])


def _literature_density_notes():
    """formula -> note of scripts/build_oxides_csv.py LITERATURE_DENSITY, read from the source's syntax tree (the parser joins the
    adjacent string literals a note is written as), so the module is not imported (importing it loads .env)."""
    tree = ast.parse((ROOT / "scripts" / "build_oxides_csv.py").read_text())
    node = next(n.value for n in tree.body if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "LITERATURE_DENSITY")
    return {k.value: v.elts[1].value for k, v in zip(node.keys, node.values)}


def _ri_comments(path):
    return str(yaml.safe_load(open(RI / "data" / path)).get("COMMENTS") or "")


def test_quoted_evidence_is_verbatim_in_its_source():
    build = (ROOT / "scripts" / "build_oxides_csv.py").read_text()
    notes = _literature_density_notes()
    flags = pd.read_csv(ROOT / "data" / "oxides_50.csv").set_index("idx")["flags"]
    evidence = "\n".join(GAPS["evidence"])
    density_notes = [
        "literature: fused silica, standard value",
        "literature: fused (vitreous) GeO2, commonly cited value",
        "literature: amorphous Ta2O5 thin film, commonly cited value (vs 8.37 crystalline)",
        "literature: evaporated amorphous SiO film, commonly cited value",
    ]
    for formula, note in zip(("SiO2", "GeO2", "Ta2O5", "SiO"), density_notes):
        assert notes[formula] == note and note in evidence
    nb_inference = ("amorphous inferred from the Franta 2024 RI.info dataset's deposition method -- magnetron sputtering, no anneal step "
                    "mentioned in its RI.info comments; the Franta paper itself was not directly accessed to confirm")
    assert nb_inference in notes["Nb2O5"] and nb_inference in flags[33] and nb_inference in evidence
    assert "took first/primary (14464-46-1)" in flags[38] and "took first/primary (14464-46-1)" in evidence
    comment_text = " ".join(line.strip().lstrip("#").strip() for line in build.splitlines() if line.strip().startswith("#"))
    assert "SiO confirmed manually" in comment_text  # a comment wrapped across two lines, compared re-joined

    assert _ri_comments("main/SiO2/nk/Malitson.yml").strip() == "Fused silica, 20 °C"
    franta = _ri_comments("main/Nb2O5/nk/Franta.yml")
    assert "Deposited by magnetron sputtering" in franta and "amorph" not in franta.lower()  # structure never stated
    assert _ri_comments("main/SiO/nk/Hass.yml") == ""  # no sample description at all
    assert "Fleming 1984: Fused germania" in (RI / "catalog-nk.yml").read_text()


def test_tracked_tasks_record_the_blocking_chain():
    for task in ("oxide_density_labels_and_polymorph", "density_provenance_upgrade", "material38_identity_correction",
                 "oxide_amorphous_migration"):
        assert task in open_tasks() and task in DOC
    assert task_detail("oxide_amorphous_migration")["blocking_on"] == "oxide_density_labels_and_polymorph"
    assert task_detail("oxide_density_labels_and_polymorph")["blocking_on"] == "density_provenance_upgrade"
    assert set(task_detail("density_provenance_upgrade")["affected_materials"]) == {"SiO2", "GeO2", "Ta2O5", "SiO", "Nb2O5"}
    assert set(task_detail("oxide_density_labels_and_polymorph")["affected_materials"]) == {"Nb2O5", "SiO", "SiO2", "Ta2O5"}
    assert task_detail("material38_identity_correction")["affected_materials"] == ["SiO2"]


def test_evidence_doc_states_the_fix_was_not_implemented_and_why():
    assert "was not implemented" in DOC
    for needle in ("Case A", "Case B", "Case D", "BLOCKED", "20 physical", "CatalogError", "14464-46-1", "sources id 4"):
        assert needle in DOC
