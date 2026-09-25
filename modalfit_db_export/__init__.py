"""
modalfit_db_export -- materials-db SQLite -> ModalFit slab-model JSON
=====================================================================
Give it a database file and an output directory; it connects, reads, and
writes ModalFit-compatible JSON (plus the sidecar n,k CSVs those JSONs
reference).

    from modalfit_db_export import export_stack_json, export_all_layers

    # one finished stack, ready to load in ModalFit
    export_stack_json(
        db_path="data/materials_oxide_test.db",
        out_dir="out/my_sample",
        layers=[{"material": "TiO2", "dataset_label": "rutile",
                 "thickness_a": 500.0, "roughness_a": 5.0}],
        substrate="Silicon",
    )

    # or every material in the database, one layer JSON each
    export_all_layers(db_path="data/materials_oxide_test.db", out_dir="out/all")

Requires the standard library only. pandas is optional and used solely to
enrich layers with a Materials Project mp_id when per-batch enrichment
CSVs sit beside the database; without it that one field is None.

See README.md for the pipeline in pseudocode, SCHEMA_NOTES.md for what
each emitted field means and which ModalFit code reads it, and contract.py
for the pinned ModalFit commit every schema assumption was verified
against.
"""

from .exporter import (
    ExportError,
    KNOWN_EXCLUSIONS,
    RESOLVED_OPTICAL_SOURCE_CITATION,
    export_layer,
    export_stack,
)
from .bulk import export_all_layers, export_stack_json, list_materials
from .contract import (
    MODALFIT_COMMIT_SHA,
    MODALFIT_REPO_URL,
    CONFIRMED_BEHAVIORS,
)

__all__ = [
    # write JSON to disk (the drop-in entry points)
    "export_stack_json", "export_all_layers", "list_materials",
    # return dicts, write only the sidecar CSVs (upstream API, unchanged)
    "export_layer", "export_stack",
    # errors / reference data
    "ExportError", "KNOWN_EXCLUSIONS", "RESOLVED_OPTICAL_SOURCE_CITATION",
    "MODALFIT_COMMIT_SHA", "MODALFIT_REPO_URL", "CONFIRMED_BEHAVIORS",
]

__version__ = "1.0.0"
