"""launcher/library_export.py
==============================
Builds a ModalFit "material library" JSON: the format
slab_model_builder.py's OWN "Load Library..." button reads, letting a
user browse and apply any of this catalog's materials directly inside
ModalFit's native stack-BUILDER tool -- a different, complementary
workflow from the rest of this launcher (which assembles a whole stack
externally via the CLI and hands ModalFit one finished model to predict/
fit). slab_model_builder.py is its own standalone Tkinter app, separate
from model_predictor.py; this module never touches its source, same
wrapper-not-fork discipline as modalfit_bridge.py.

Schema confirmed by reading slab_model_builder.py directly (pinned
commit, see export/modalfit_contract.py), not guessed:
  - _load_material_library() (line 1110) accepts {"materials": [...]}
    or a bare list.
  - MaterialPickerDialog (line 600) displays "label" and filters on
    "label"/"material_type" substrings -- nothing else is visible in the
    picker list itself, so density confidence must be baked into the
    label text to stay visible at SELECTION time, matching this whole
    launcher's standing principle (see catalog.describe_row()) rather
    than only showing up after the fact in the descriptors readout.
  - _apply_library_to_layer()/_apply_library_to_substrate() (line 1133,
    1168) read "optical" (same {"model", "params"} shape export_layer()
    already produces -- confirmed via OpticalModelEditor's own
    get_data/set_data, line 146), "scattering.sld_real"/"sld_imag" (same
    shape as export_layer()'s own "scattering" alias block -- x-ray SLD,
    the convention already established for cross-tool compatibility),
    and "molecular_descriptors" (an opaque passthrough blob,
    MolecularDescriptorsEditor's own docstring: "Populated from material
    library import", displayed as read-only formatted JSON, not consumed
    by any physics -- used here to carry export_layer()'s full
    "materials_db" citation/confidence block, so a user browsing the
    library still sees density_confidence and citations, not just SLD
    numbers).
  - substrate_editor._name.set(name) only takes effect if `name` is one
    of SubstrateEditor's fixed dropdown values (line 38:
    ["silicon","silicon_oxide","gold","qcm_sensor","glass","sapphire",
    "other"]). For the 4 materials with a real, unambiguous
    correspondence (Si -> "silicon", SiO2 -> "silicon_oxide", Au ->
    "gold", Al2O3 -> "sapphire" -- each confirmed the ONLY material in
    this DB with that formula before mapping it), `name` is set to the
    matching dropdown value instead of the DB's own display name, so
    applying the library entry actually updates the substrate category
    dropdown too, not just its optical/scattering/descriptors data.
    Every other material keeps its real DB name -- ModalFit's dropdown
    genuinely has no category for e.g. HfO2 or MgO, so there's nothing
    more correct to map those to; forcing them to "other" would lose the
    real name for zero gain, since substrate_editor only checks
    membership, never displays `name` itself.
  - Layers have no such name field at all -- library-to-layer application
    is unaffected by the substrate-name mapping above.
  - material_type is freeform text in MaterialPickerDialog's own filter,
    but LayerEditor's OWN material_type dropdown (used outside library
    import) is restricted to MATERIAL_TYPES (line 36: ["polymer","oxide",
    "metal","semiconductor","organic","inorganic","bulk_media","other"]),
    a different vocabulary than this project's own anion-based
    _classify_material_type() (oxide/fluoride/nitride/sulfide/unknown).
    "oxide" already matches directly. Everything else maps to
    "inorganic" -- true without exception for every material in this
    catalog (oxides, fluorides, nitrides, sulfides, and pure elements are
    all inorganic solids), rather than guessing "metal" vs.
    "semiconductor" per pure element (Boron, Silicon, Diamond, and
    Graphite are not metals; getting that classification wrong would be
    a worse outcome than the honest, broader "inorganic").

Deliberately NOT thickness/roughness/viscoelastic: those describe one
specific film INSTANCE (a given deposition's measured thickness, a
polymer's measured modulus), not a reusable material definition. Leaving
"structural" out of an entry means slab_model_builder.py's own
_apply_library_to_layer() correctly leaves whatever thickness/roughness
the user already had, rather than overwriting it with a template value
that was never really a property of the material itself.

Absolute sidecar paths, NOT relative (the one real convention difference
from export_stack()'s own JSON, and worth being explicit about): a stack
JSON's relative n,k path is resolved against THAT model file's own
directory via model_predictor.py's _json_dir tracking (see
modalfit_bridge.py's docstring) -- but a material LIBRARY is loaded once
and reused across many future model-building sessions, each saved to an
arbitrary, unknown-in-advance directory. A relative path would only
resolve if that future save directory happened to match the library's
own directory, which cannot be assumed. Sidecar CSVs are therefore
written to a persistent location (not a temp directory -- see
scripts/build_modalfit_material_library.py) and referenced by absolute
path, matching physics.py's own _resolve_nk_path()'s documented "try
fpath as-is" first branch (an absolute path resolves regardless of
json_dir).
"""

from pathlib import Path
from typing import Optional

from materials_db.export.modalfit import ExportError, _classify_material_type, export_layer
from materials_db.launcher.catalog import list_materials
from materials_db.pipeline.process_condition import DENSITY_BULK_APPROXIMATION

# slab_model_builder.py's SubstrateEditor only recognizes these 7 fixed
# dropdown values (line 38) -- mapped here for the 4 formulas that
# genuinely, unambiguously correspond to one (each confirmed the ONLY
# material in this DB with that formula; see this module's docstring).
# Everything else keeps its real DB name -- there's no more-correct
# target to map e.g. HfO2 or MgO to, and forcing "other" would lose the
# real name for no benefit (SubstrateEditor only checks membership).
_MODALFIT_SUBSTRATE_NAME_BY_FORMULA = {
    "Si": "silicon",
    "SiO2": "silicon_oxide",
    "Au": "gold",
    "Al2O3": "sapphire",
}

# ModalFit's own LayerEditor material_type vocabulary (line 36) is
# different from this project's anion-based _classify_material_type().
# "oxide" is the one value both sides already share; everything else
# maps to "inorganic" -- broadly, unconditionally true for every
# material in this catalog, rather than guessing a finer ModalFit
# category (e.g. "metal" vs. "semiconductor") per pure element, which
# would be wrong for several of them (Boron, Silicon, Diamond, Graphite
# are not metals).
_MODALFIT_MATERIAL_TYPE = {"oxide": "oxide"}


def _to_modalfit_material_type(our_material_type: str) -> str:
    return _MODALFIT_MATERIAL_TYPE.get(our_material_type, "inorganic")


def build_library_entry(db, name: str, polymorph: Optional[str], out_dir) -> dict:
    """One slab_model_builder.py library entry for a single DB material.
    Raises ExportError exactly when export_layer() would (missing
    density, no optical data, ambiguous dataset_label) -- callers
    iterating the whole catalog should catch this per-material, the same
    "report what failed, don't let one bad entry kill the whole batch"
    treatment export_all_materials_modalfit.py already uses."""
    out_dir = Path(out_dir).resolve()
    layer = export_layer(db, name, polymorph, nk_csv_dir=out_dir, role="layer")
    formula = layer["molecular"]["formula"]

    optical = dict(layer["optical"])
    if optical.get("model") == "Tabulated n,k":
        rel_file = optical["params"]["file"]
        optical["params"] = dict(optical["params"], file=str(out_dir / rel_file))

    confidence = layer["molecular"]["density_confidence"]
    flag = " *** BULK_APPROXIMATION density ***" if confidence == DENSITY_BULK_APPROXIMATION else ""
    display_label = f"{name} ({formula}) -- {confidence}{flag}"

    descriptors = dict(layer["molecular"])
    descriptors.update(layer["materials_db"])

    our_material_type = _classify_material_type(formula)

    return {
        "name": _MODALFIT_SUBSTRATE_NAME_BY_FORMULA.get(formula, name),
        "label": display_label,
        "material_type": _to_modalfit_material_type(our_material_type),
        "optical": optical,
        "scattering": layer["scattering"],
        "molecular_descriptors": descriptors,
    }


def build_material_library(db, out_dir) -> tuple:
    """Every selectable (non-named-exclusion) material in `db`, as a
    slab_model_builder.py library. Returns (library_dict, errors) --
    errors is a list of (name, message) for any material that failed
    (should be empty; the two named exclusions are already filtered out
    by list_materials()'s own selectable flag before this ever runs).
    Never raises on a per-material failure -- reports it instead, same
    reasoning as export_all_materials_modalfit.py's KNOWN_EXCLUSIONS
    handling."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    errors = []
    for row in list_materials(db):
        if not row["selectable"]:
            continue
        try:
            entries.append(build_library_entry(db, row["name"], row["polymorph"], out_dir))
        except ExportError as e:
            errors.append((row["name"], str(e)))

    library = {
        "library_name": f"materials-db ({len(entries)} materials)",
        "materials": entries,
    }
    return library, errors
