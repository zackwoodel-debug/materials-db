#!/usr/bin/env python3
"""
modalfit_export.py -- materials-db SQLite -> ModalFit slab-model JSON
======================================================================
Point it at a materials database file and an output directory; it
connects, reads, and writes ModalFit-compatible slab-model JSON, plus the
sidecar tabulated-n,k CSV each layer's optical block points at.

    materials_oxide_test.db  ->  modalfit_export.py  ->  stack.json
    (SQLite)                                             + TiO2_rutile_nk.csv
                                                         + SiO2_amorphous_nk.csv
                                                         + Si_diamond_cubic_nk.csv

ONE FILE. Standard library only. No install step, no package layout, no
assumptions about surrounding directories -- drop it anywhere and import
it. (pandas is optional; see OPTIONAL ENRICHMENT below.)


QUICKSTART
----------
    # what's in the database?
    python3 modalfit_export.py --db materials_oxide_test.db --list

    # one stack: 500 A rutile TiO2 over 1000 A SiO2 on a Si substrate
    python3 modalfit_export.py --db materials_oxide_test.db --out out/sample \
        --layer "TiO2@rutile:500:5" "SiO2:1000:3" \
        --substrate Silicon --substrate-roughness 4

    # every material in the database, one layer JSON each
    python3 modalfit_export.py --db materials_oxide_test.db --out out/all

Same three things from Python:

    from modalfit_export import list_materials, export_stack_json, export_all_layers

    list_materials("materials_oxide_test.db")

    export_stack_json(
        db_path="materials_oxide_test.db",
        out_dir="out/sample",
        layers=[
            {"material": "TiO2", "dataset_label": "rutile",
             "thickness_a": 500.0, "roughness_a": 5.0},
            {"material": "SiO2", "thickness_a": 1000.0, "roughness_a": 3.0},
        ],
        substrate="Silicon",
        substrate_roughness_a=4.0,
    )   # -> Path("out/sample/stack.json")

    export_all_layers("materials_oxide_test.db", "out/all")

KEEP THE JSON AND ITS CSVs TOGETHER. Each layer's optical.params.file is a
bare filename resolved RELATIVE TO THE JSON. Moving the JSON on its own
silently breaks every tabulated-n,k layer -- see LIMITATIONS (1).


THE PIPELINE, IN PSEUDOCODE
---------------------------
This is the whole thing. Everything below is SECTION 4 restated without
the error handling and provenance bookkeeping.

  FUNCTION export_stack_json(db_path, out_dir, layers, substrate):

      connection = sqlite3.connect(db_path)        # plain stdlib sqlite3
      MAKE DIRECTORY out_dir

      # 1. Resolve every label FIRST, before writing anything.
      #    A label is the layer's identity: it names the sidecar CSV AND
      #    becomes ModalFit's fit-parameter key ("SiO2_amorphous:thick").
      #    Two layers sharing a label would overwrite each other's CSV and
      #    collapse into ONE fittable parameter -- a repeated-unit stack
      #    (Bragg mirror, superlattice) would silently stop being fittable.
      substrate_label = resolve_label(connection, substrate)
      seen = {substrate_label: 1}                  # substrate seeds the count
      FOR each layer IN layers:
          base = layer.label OR resolve_label(connection, layer.material)
          seen[base] += 1
          final_label = base IF seen[base] == 1 ELSE base + "#" + seen[base]

      # 2. Build each entry (see export_layer below).
      stack = [ ambient_entry ]                    # air: exact-zero SLD
      FOR each layer, final_label:
          stack.APPEND( export_layer(..., role="layer",     label=final_label) )
      stack.APPEND(     export_layer(..., role="substrate", label=substrate_label) )

      # 3. Serialize. Ambient first, films outermost-in, substrate last.
      WRITE out_dir/stack.json  <-  {stack_id, sample_id, version,
                                     provenance, n_layers, stack}
      RETURN path to stack.json


  FUNCTION export_layer(connection, material_name, dataset_label, out_dir, label):

      # ---- A. Identify the material ---------------------------------
      row = SELECT material_id, name, formula FROM materials WHERE name = ?
      IF no row:
          row = SELECT ... WHERE formula = ?
          IF more than one row:
              RAISE ExportError      # "C" is both Diamond and Graphite.
                                     # Never silently pick one.

      # ---- B. Physical properties, disambiguated by polymorph --------
      rows = SELECT dataset_label, density_g_cm3, xray_sld, neutron_sld,
                    source_id
             FROM physical_properties WHERE material_id = ?

      # dataset_label packs the polymorph into its first " | " segment:
      #   "rutile | xray_sld_real | periodictable_CuKalpha" -> "rutile"
      #   "xray_sld_real | periodictable_CuKalpha"          -> no polymorph
      #   "density_MP_DFT"                                  -> no polymorph
      # so the first segment is only a polymorph if it is NOT a quantity
      # marker ("density_", "xray_sld_real", ...) and NOT an "AuthorYYYY"
      # source label. Splitting blindly on " | " mistakes a quantity for
      # a polymorph -- that was a real bug, see _polymorph_prefix.
      polymorphs = DISTINCT polymorph_prefix(r.dataset_label) FOR r IN rows

      IF dataset_label given:  chosen = the polymorph it matches
      ELIF exactly one:        chosen = that one
      ELSE:                    RAISE ExportError   # caller must say which

      density, xray_sld_real/imag, neutron_sld_real/imag
          = the rows under `chosen`
      IF density IS NULL:
          RAISE ExportError  # refnx's MaterialSLD takes density as a
                             # REQUIRED positional arg with no fallback.
                             # Emitting null here means ModalFit guesses.
                             # Refuse instead.

      # ---- C. Optical dispersion: pick exactly ONE axis --------------
      candidates = DISTINCT dataset_label FROM optical_dispersion
                   WHERE material_id = ? AND polymorph_prefix == chosen
      IF dataset_label matches one exactly: use it
      ELIF only one candidate:              use it
      ELSE:                                 prefer isotropic, else o-ray,
                                            else alphabetically first
                                            AND PRINT what was chosen
          # ModalFit's optical block models an ISOTROPIC material. A
          # birefringent material's o/e axes cannot both be represented
          # in one layer. A real simplification, announced, not hidden.

      nk_rows = SELECT wavelength_nm, n, k FROM optical_dispersion
                WHERE material_id = ? AND dataset_label = ?
                ORDER BY wavelength_nm

      # ---- D. Units: one boundary, not scattered per field -----------
      values = to_modalfit_units(density, slds, thickness, roughness)
          # Every field is currently an IDENTITY pass-through -- the DB
          # and ModalFit already agree:
          #     SLD        1e-6 A^-2     density             g/cm3
          #     wavelength nm            thickness/roughness A
          # Kept as one function anyway, so a future real mismatch has
          # exactly one place to fix.

      # ---- E. Sidecar n,k CSV ----------------------------------------
      filename = sanitize(label) + "_nk.csv"   # "/" too: "corundum/sapphire"
      WRITE out_dir/filename:
          header  wavelength_nm, n, k
          rows    each nk_row, with k=0.0 where k IS NULL
          # ModalFit loads this with np.loadtxt, which needs every cell to
          # parse as a float -- an empty string for a missing k crashes.
          # 0.0 = transparent/non-absorbing. Count printed, never silent.

      # ---- F. Density confidence decides the FIT BOUNDS --------------
      IF "bulk_elemental_approximation" IN density's dataset_label:
          confidence = "bulk_approximation"
          bounds     = {min: density * 0.70, max: density * 1.02}
          # A bulk density standing in for an unmeasured film. Films are
          # usually LESS dense than bulk (voids, columnar growth), rarely
          # denser -- hence asymmetric, not +-X%.
      ELSE:
          confidence = "verified"
          bounds     = {min: density, max: density}
          # Zero-width: pins it, so a caller who marks every density
          # vary=True cannot move a value we are confident in.

      # ---- G. Assemble ------------------------------------------------
      RETURN {
        label, role, material_type,      # material_type from the anion:
                                         # O->oxide, F->fluoride,
                                         # N->nitride, S->sulfide
        molecular:  {formula, density_g_cm3, density_confidence,
                     density_bounds},
        structural: {thickness: {value,min,max},
                     roughness: {value,min,max}},
        optical:    {model: "Tabulated n,k", params: {file: filename}},
        xray:       {sld_real, sld_imag},  # <- what the LIVE app reads
        neutron:    {sld_real, sld_imag},  #    (physics.py _get_sld)
        scattering: {sld_real, sld_imag},  # <- alias, x-ray, for the
                                           #    standalone model_predictor.py
        materials_db: {dataset_label, optical_dataset_label, mp_id,
                       density_confidence, density_source, optical_source}
      }

Two conventions worth stating outright, both verified against ModalFit's
fitting code rather than inferred:

  - roughness describes the interface ABOVE its layer, never below --
    refnx's own sld_obj(thick, rough) convention. Get it backwards and
    every interface attaches to the wrong side with no error.
  - A positive imaginary SLD means absorption. Both of ModalFit's
    consumption paths agree with that sign as-is; no conjugation.


WHAT THE DATABASE MUST PROVIDE
------------------------------
Any database satisfying this shape works -- no particular material set is
assumed.

  materials            material_id, name (UNIQUE -- the real identity
                       key), formula
  physical_properties  material_id, dataset_label, density_g_cm3,
                       xray_sld, neutron_sld, source_id
  optical_dispersion   material_id, dataset_label, wavelength_nm, n, k,
                       source_id
  sources              source_id, doi, title, authors, journal, year

dataset_label carries polymorph, quantity and provenance in one string
("rutile | xray_sld_real | periodictable_CuKalpha"). Section B of the
pseudocode is how it is parsed; that convention is why no schema change
was needed to add polymorph support.

ALWAYS PASS `name`, NOT `formula`, WHEN YOU CAN -- name is UNIQUE,
formula is not (Diamond and Graphite are both "C").

OPTIONAL ENRICHMENT: if per-batch CSVs with `formula` and `mp_id` columns
sit BESIDE the database file, each layer's materials_db.mp_id is filled
in from them. That needs pandas. Without the CSVs, without pandas, or
both, that single field is None and nothing else changes.


LIMITATIONS
-----------
Real, known, and not worked around. Stated so nobody rediscovers them.

1. SIDECAR n,k CSVs ONLY RESOLVE IN THE STANDALONE DESKTOP TOOL.
   physics.py:_resolve_nk_path falls back to json_dir + file, but
   json_dir comes from entry["_json_dir"], which ONLY model_predictor.py
   ever sets. The live web app's upload route (/api/model/upload) accepts
   exactly one JSON file, never sets _json_dir, and has no route for a
   companion CSV at all. So a stack exported here loads correctly in the
   desktop tool, and its tabulated optical data does NOT resolve in the
   web app unless the path happens to be absolute and reachable on the
   server host. THIS IS THE SINGLE BIGGEST THING TO FIX IF THIS GETS
   MERGED UPSTREAM. See CONFIRMED_BEHAVIORS["optical_nk_path_resolution"]
   in SECTION 3 for the file:line evidence.

2. ONE OPTICAL AXIS PER LAYER. ModalFit's optical block is isotropic; a
   birefringent material's o/e (or biaxial alpha/beta/gamma) axes cannot
   both live in one layer. The exporter picks one, prefers isotropic ->
   o-ray, and prints which it chose. It never silently averages them.

3. AMBIENT IS NOT DATABASE-DRIVEN. The database holds thin-film solids --
   no liquids or gases -- so ambient="air" is an exact-zero-SLD
   placeholder, correct to ~4 decimal places for air/vacuum. For a liquid
   ambient (D2O, H2O) pass a pre-built entry dict to export_stack().

4. MISSING k BECOMES 0.0. Many source datasets are n-only. The count is
   printed per file, never silent, but it IS an approximation:
   transparent/non-absorbing, reasonable for visible-range dielectrics,
   wrong for an absorbing film.

5. TWO MATERIALS CANNOT BE EXPORTED and this is expected, not a bug --
   see KNOWN_EXCLUSIONS in SECTION 4. Both lack any citable density, and
   the exporter refuses to emit a null density rather than letting
   ModalFit guess.


PROVENANCE
----------
SECTION 4's translation logic is materials-db's
src/materials_db/export/modalfit.py, UNCHANGED. Three couplings to that
repo's layout were rewired, each marked `# DROP-IN:` inline:

  1. The citation table (SECTION 2) and density-confidence helpers
     (SECTION 1) were imported from scripts/ via a sys.path.insert and
     from the ingestion pipeline package; they are inlined here.
  2. _ROOT / DEFAULT_DB -- a hardcoded path into the checkout -- are
     gone. The database is always an explicit argument, so this can never
     silently read the wrong database.
  3. _lookup_mp_id() globbed that same hardcoded data/ directory and
     imported pandas unconditionally. It now takes the directory as a
     parameter (defaulting to the database's own directory, which
     reproduces the original behavior exactly) and degrades to None
     without pandas.

VERIFIED AGAINST THE ORIGINAL: exporting the same stack through both
paths produces byte-identical JSON (modulo the intentionally re-labelled
provenance.generated_by) and byte-identical sidecar CSVs. The
full-catalog run exports 133/135 materials with the skip set matching
KNOWN_EXCLUSIONS exactly.

SECTION 3 pins the ModalFit commit every schema assumption was verified
against. ModalFit's own README has already diverged from its actual
behavior twice during this integration -- it documents an examples/
directory that does not exist, and labels SLD units inconsistently
between its own LayerEditor ("x1e-6 A^-2") and SubstrateEditor ("A^-2")
for functionally identical fields. So nothing here rests on
documentation; each finding cites the file and line it was confirmed
against. If exports start misbehaving, diff a fresh clone against
MODALFIT_COMMIT_SHA and re-check the cited lines -- that tells you
immediately whether it is a bug here or upstream drift.


CONTENTS
--------
  SECTION 1  Density confidence: constants and fit bounds
  SECTION 2  Optical-source citation table (phase resolutions)
  SECTION 3  Pinned ModalFit commit + confirmed schema behaviors
  SECTION 4  The exporter: DB -> ModalFit layer/stack dicts
  SECTION 5  Writing JSON to disk (the db-path + out-path entry points)
  SECTION 6  Command line interface
"""

import argparse
import csv
import csv as _csv
import json
import re
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Optional

__version__ = "1.0.0"

__all__ = [
    # write JSON to disk (the drop-in entry points)
    "export_stack_json", "export_all_layers", "list_materials",
    # return dicts, write only the sidecar CSVs (upstream API, unchanged)
    "export_layer", "export_stack",
    # errors / reference data
    "ExportError", "KNOWN_EXCLUSIONS", "RESOLVED_OPTICAL_SOURCE_CITATION",
    "MODALFIT_COMMIT_SHA", "MODALFIT_REPO_URL", "CONFIRMED_BEHAVIORS",
]


# ==========================================================================
# SECTION 1 -- DENSITY CONFIDENCE
# ==========================================================================
# From materials-db src/materials_db/pipeline/process_condition.py.
#
# The distinction these encode, in one line: a density is VERIFIED when the
# stored value is trustworthy for the actual sample the optical data was
# measured on, and a BULK_APPROXIMATION when a bulk/single-crystal density is
# standing in for an unmeasured thin film. That difference is not cosmetic --
# it changes the fit bounds emitted below, and therefore what a fit is
# allowed to do with the density.

DENSITY_VERIFIED = "verified"
DENSITY_BULK_APPROXIMATION = "bulk_approximation"

# The density_source value stored inside physical_properties.dataset_label
# (via the "density_{density_source}" convention) for a bulk-approximation
# density. Distinct from "MP_DFT" / "experimental lattice params" /
# "literature", all of which mean a value that IS trusted for the actual
# sample measured -- a genuinely bulk/single-crystal sample's bulk density
# is correct, not an approximation -- and so count as DENSITY_VERIFIED.
#
# Named for the case that motivated it (pure elements with no measured
# film density), but the mechanism is not element-specific: a COMPOUND
# whose only optical data is an uncharacterized sputtered/ALD/annealed
# thin film with no stated density (TiN, VN, EuS) has the identical
# problem -- a DFT bulk crystal density standing in for an unmeasured
# film. Use this same value for that case rather than inventing a second
# bulk-fallback marker.
BULK_ELEMENTAL_APPROXIMATION = "bulk_elemental_approximation"


def bulk_approximation_density_bounds(bulk_density_g_cm3: float) -> dict:
    """Physically-motivated fit bounds for a bulk_elemental_approximation
    density: evaporated/sputtered films are commonly LESS dense than bulk
    (voids, columnar/porous growth), rarely denser (occasional
    ion-bombardment-compacted sputtered films aside) -- asymmetric bounds
    matching that direction, not a naive +-X% or ModalFit's generic
    [0.5x, 2x] ParamSpec fallback (physically implausible on the high side
    for a single-element film). Emitted as "molecular.density_bounds" so a
    fit can vary density within a defensible range instead of either
    trusting a wrong fixed value or an unconstrained one."""
    return dict(min=bulk_density_g_cm3 * 0.70, max=bulk_density_g_cm3 * 1.02)


def verified_density_bounds(density_g_cm3: float) -> dict:
    """Zero-width bounds for a DENSITY_VERIFIED value: pins it, so a
    caller who naively marks every layer's density vary=True (ModalFit's
    physics.py extract_params() auto-generates a density ParamSpec for
    every layer with molecular.density_g_cm3 set, regardless of
    confidence) cannot accidentally move a value this pipeline is
    confident in."""
    return dict(min=density_g_cm3, max=density_g_cm3)


# ==========================================================================
# SECTION 2 -- OPTICAL-SOURCE CITATIONS
# ==========================================================================
# The merged RESOLVED_OPTICAL_SOURCE_CITATION table materials-db assembles
# from its two per-batch material-list modules.
#
# Keyed by FORMULA (not material name -- these are phase resolutions, and a
# formula is what identifies the published dataset). export_layer() merges
# each entry's verification_note into the optical citation it reads from the
# DB's own `sources` table: the note records HOW the phase behind a published
# n,k dataset was confirmed, which `sources` has no column for.

RESOLVED_OPTICAL_SOURCE_CITATION = {
    'As2S3': dict(
        doi=None,
        title='AMTIR-6 (As2S3) product datasheet',
        authors='Amorphous Materials, Inc.',
        journal=None,
        year=None,
        verification_note='Reuses the SiO2 quartz-vs-fused-silica '
                          "resolution verbatim. RI.info's 'Slavich' dataset "
                          '(biaxial alpha/beta/gamma) is necessarily '
                          'CRYSTALLINE (orpiment) since biaxial optics '
                          'require an ordered crystal -- switched default '
                          "to 'Rodney' (Rodney, Malitson, King 1958), whose "
                          "COMMENTS state 'Arsenic trisulfide glass. 25 C' "
                          'explicitly, meeting the same evidentiary bar as '
                          "Ta2O5's 'Amorphous thin film' COMMENTS. "
                          "Independently corroborated: 'Synowicki' (2004) "
                          "titles its dataset 'a-As2S3' (amorphous "
                          'notation), contrasted directly against '
                          "'c-ZrO2'/'c-MgO' in the SAME paper.",
    ),
    'HgS': dict(
        doi=None,
        title="Bond, W. L. et al. 1967 (RI.info page COMMENTS: 'alpha-HgS')",
        authors='Bond, W.L. et al.',
        journal=None,
        year=1967,
        verification_note="RI.info's own page name states the measured "
                          "phase directly: 'Bond et al. 1967: alpha-HgS' "
                          '(cinnabar). Cross-checked against MP (not just '
                          "trusted from the page name alone) -- MP's "
                          'lowest-energy_above_hull entry is metacinnabar '
                          '(F-43m #216, a DIFFERENT phase), so this needed '
                          'the same EXPECTED_SPACEGROUP override treatment '
                          'as CeF3/BN despite the RI.info metadata already '
                          'stating the correct phase name.',
    ),
    'Ta2O5': dict(
        doi='10.1063/1.4819325',
        title='Infrared optical properties of amorphous and nanocrystalline '
              'Ta2O5 thin films',
        authors='Bright, T.J.; Watjen, J.I.; Zhang, Z.M.; Muratore, C.; '
                'Voevodin, A.A.; Koukis, D.I.; Tanner, D.B.; Arenas, D.J.',
        journal='Journal of Applied Physics',
        year=2013,
        verification_note="RI.info's COMMENTS field for this dataset states "
                          '"Amorphous thin film" explicitly -- not a '
                          'crystalline phase name.',
    ),
    'TeO2': dict(
        doi='10.1103/PhysRevB.4.3736',
        title='Optical properties of single-crystal paratellurite (TeO2)',
        authors='Uchida, N.',
        journal='Physical Review B',
        year=1971,
        verification_note='Paper title explicitly names the measured phase: '
                          'paratellurite.',
    ),
    'VO2': dict(
        doi='10.1016/j.solmat.2019.110260',
        title='Thermochromic VO2-based smart radiator devices with ultralow '
              'refractive index cavities for increased performance',
        authors='Beaini, R.; Baloukas, B.; Loquai, S.; Klemberg-Sapieha, '
                'J.E.; Martinu, L.',
        journal='Solar Energy Materials and Solar Cells',
        year=2020,
        verification_note="70nm film measured at 25 C, below VO2's ~68 C "
                          'metal-insulator transition -- confirms '
                          'monoclinic M1 (insulating) phase.',
    ),
}


# ==========================================================================
# SECTION 3 -- PINNED MODALFIT COMMIT AND CONFIRMED BEHAVIORS
# ==========================================================================
# Every schema assumption in SECTION 4, with the file:line in ModalFit's own
# source it was verified against. See PROVENANCE in the module docstring for
# why this is code and not a README note.

MODALFIT_REPO_URL = "https://github.com/agauer/modalfit"
MODALFIT_COMMIT_SHA = "4eef754295be929f77b04dcfcd8b6c882ba5f101"
MODALFIT_COMMIT_DATE = "2026-08-12 13:28:07 -0400"
VERIFIED_ON = "2026-09-11"

# Each entry: exact file(s)/line(s) in the pinned ModalFit commit the
# finding was confirmed against, and what was confirmed. "empirical" entries
# were additionally confirmed by installing ModalFit's real dependencies
# (refnx, periodictable) and calling its actual code, not just reading it.
CONFIRMED_BEHAVIORS = {
    "optical_nk_path_resolution": dict(
        file="physics.py", lines="110-119, 170-213",
        function="_resolve_nk_path, nk_tabulated",
        finding=(
            "_resolve_nk_path(fpath, json_dir) tries fpath as-is (resolves "
            "against CWD if relative, or as an absolute path), then "
            "os.path.join(json_dir, fpath). json_dir comes from "
            "entry['_json_dir'], which is ONLY ever set by the standalone "
            "model_predictor.py Tkinter tool (model_predictor.py:549-552, "
            "os.path.dirname(os.path.abspath(path)) when loading a model file "
            "from disk). The live web app's upload flow (server.py:98-112 "
            "model_upload -> server.py:69-81 _apply_model_payload -> "
            "physics.py:1287-1310 normalize_stack) never sets _json_dir at "
            "all, and server.py has no route to upload a companion CSV "
            "(server.py's only model-related upload route, /api/model/upload, "
            "accepts exactly one JSON file). CONSEQUENCE: this exporter's "
            "sidecar n,k CSVs, written relative to the exported JSON's own "
            "directory, only resolve when the model is opened via the "
            "standalone desktop tool -- not via the live web app, unless the "
            "path happens to be absolute and reachable on whatever machine "
            "runs the Flask server."
        ),
    ),
    "material_sld_density_required": dict(
        file="refnx (ModalFit's own dependency, imported inside physics.py)",
        lines="MaterialSLD.__init__ signature, confirmed via inspect.getsource",
        function="MaterialSLD.__init__; physics.py:_get_molecular (324-333)",
        finding=(
            "MaterialSLD(self, formula, density, probe='neutron', "
            "wavelength=1.8, name=''): density is a required positional "
            "parameter with no default and no internal lookup/inference -- "
            "it's wrapped directly as a Parameter via possibly_create_parameter"
            "(density, name='density', units='g / cm**3'). ModalFit's own "
            "physics.py:_get_molecular reads molecular.density_g_cm3 or "
            "molecular.density (both key names aliased) and passes it "
            "straight through with no fallback. CONSEQUENCE: this exporter "
            "must always supply density explicitly, and refuses to export a "
            "layer with none rather than letting ModalFit guess."
        ),
    ),
    "units_wavelength_nm_vs_thickness_angstrom": dict(
        file="physics.py, slab_model_builder.py",
        lines="physics.py:134 (nk_cauchy), 170-213 (nk_tabulated), "
              "slab_model_builder.py:708-709 (GUI label)",
        function="nk_cauchy, nk_tabulated",
        finding=(
            "Wavelength (optical inputs, the tabulated n,k CSV's wavelength "
            "column) is nm: nk_cauchy does wl_um = wl_nm / 1000.0 "
            "(physics.py:134), and nk_tabulated's loader auto-detects and "
            "corrects micron-scale data via a median<50 heuristic "
            "(physics.py:186-193), with an explicit code comment warning "
            "about exactly this silent-unit-mismatch failure mode. "
            "Thickness/roughness is Angstrom: labelled 'Thickness (Å)' in the "
            "GUI (slab_model_builder.py:708-709) and used directly as d_A in "
            "physics.py's QCM impedance calculation (d_A * 1e-10 -> meters). "
            "Our DB stores wavelength in nm already -- no conversion needed; "
            "thickness/roughness are caller-supplied (not in the DB) and "
            "passed straight through as Angstrom."
        ),
    ),
    "xray_sld_units": dict(
        file="physics.py",
        lines="911-924 (extract_params default bounds); empirical check below",
        function="extract_params; MaterialSLD.complex (refnx)",
        finding=(
            "SLD is in units of 1e-6 A^-2 (a value of 34.5 means 34.5e-6 A^-2), "
            "matching materials-db's own convention. Confirmed two ways: (a) "
            "extract_params sets a default upper bound of max(sv*2.0, 150.0) "
            "for sld_real_xray -- only sensible if values are O(1-150) (e.g. "
            "gold ~125), not plain A^-2 (O(1e-4)). (b) EMPIRICAL: installed "
            "refnx==0.1.64 and periodictable, called "
            "MaterialSLD('TiO2', 4.2362, probe='x-ray', wavelength=1.5406)"
            ".complex(1.5406) directly -- returned 34.5176+1.7421j, matching "
            "materials_oxide_test.db's stored TiO2-rutile xray_sld_real/imag "
            "(34.5178, 1.742017) to 4 decimal places."
        ),
    ),
    "sld_block_schema_split": dict(
        file="physics.py, slab_model_builder.py, model_predictor.py, server.py",
        lines="physics.py:314-321 (_get_sld), slab_model_builder.py:502,758,920 "
              "('scattering' block), model_predictor.py:276,296 (reads "
              "'scattering'), server.py:25 (import physics as P)",
        function="_get_sld",
        finding=(
            "Two incompatible SLD schema conventions coexist in ModalFit. The "
            "GUI builder (slab_model_builder.py) persists a combined "
            "'scattering': {sld_real, sld_imag} block. The live web app "
            "(server.py imports physics as P; physics.py:_get_sld reads "
            "block_key = 'neutron' if probe=='neutron' else 'xray'; "
            "sc = entry.get(block_key, {})) reads separate top-level 'xray'/"
            "'neutron' blocks and never touches 'scattering' at all. The "
            "standalone model_predictor.py has its own third copy of this "
            "logic that DOES read 'scattering', but is not imported by "
            "server.py -- not part of the live app. This exporter targets "
            "physics.py's 'xray'/'neutron' convention (what the live app "
            "reads) and also emits a 'scattering' alias for the standalone "
            "tool's compatibility."
        ),
    ),
}


# ==========================================================================
# SECTION 4 -- THE EXPORTER
# ==========================================================================
# materials-db src/materials_db/export/modalfit.py, unchanged except for the
# three couplings marked `# DROP-IN:` inline.
#
# export_layer()  -- one material -> one ModalFit stack entry (+ its sidecar CSV)
# export_stack()  -- ambient + films + substrate -> the full slab-model dict
#
# Both RETURN dicts. SECTION 5 is what also writes the JSON to disk.

# DROP-IN (1): vendored siblings. Upstream these were
#   sys.path.insert(_ROOT/"scripts") + `from oxide_material_list import ...`
#   + `from fluoride_nitride_sulfide_material_list import ...`, merged here
#   into one dict, and `from materials_db.pipeline.process_condition import ...`.
# See each module's docstring for what was lifted and how to regenerate it.

# DROP-IN (2): _ROOT / DEFAULT_DB removed. Upstream they were
#   _ROOT = Path(__file__).resolve().parents[3]
#   DEFAULT_DB = _ROOT / "data" / "materials_oxide_test.db"
# -- a path that only resolves inside a materials-db checkout. Every public
# function here takes the database as its first argument instead; there is
# no default and no implicit lookup, so this package can never silently
# read the wrong database.

# Historical note: substrate used to be a fixed, non-DB-sourced Si
# placeholder here (density_g_cm3=2.329, xray_sld_real=20.0620,
# xray_sld_imag=0.457236). Silicon is now a real materials_oxide_test.db
# material (batch 3, verified bulk/single-crystal) and export_stack()
# resolves ANY substrate the same way it resolves a film layer -- see
# export_stack()'s docstring. Cross-checked once, for the record: routing
# "Silicon" through export_layer() reproduces these exact legacy numbers
# to displayed precision (confirmed via refnx.MaterialSLD("Si", 2.329,
# probe="x-ray") -> 20.0620+0.4573j, matching this constant exactly), so
# the switch changes WHERE the number comes from, not its value.


class ExportError(ValueError):
    """Raised for anything this exporter refuses to silently paper over:
    an ambiguous dataset_label, a missing density, no optical data, etc.
    Never emit a null/guessed value where the task requires an explicit
    error instead."""


# Named, asserted-against exclusions from the 50-material set -- a bulk
# export producing exactly these (and only these) ExportErrors is a known,
# expected outcome, not a partial failure. See
# materials-db scripts/export_all_oxides_modalfit.py, which asserts the skip set matches
# this exactly: an unexpected skip (regression) or an unexpected SUCCESS
# (this material's underlying gap got fixed) both fail loudly rather than
# silently changing what "49/50" means.
KNOWN_EXCLUSIONS = {
    "LuAl3(BO3)4": "no density available from either PubChem or Materials Project "
                   "(see materials-db data/CHECKPOINT_2_report.md) -- export_layer correctly "
                   "refuses to export a layer with no density rather than emitting "
                   "a null. Accepted, expected exclusion, not a bug.",
    "GdF3": "named exclusion (batch 2, see materials-db scripts/fluoride_nitride_sulfide_material_list.py "
            "EXCLUSION_STATE) -- MP's only entry is theoretical/unverified and structurally "
            "inconsistent with GdF3's documented room-temperature phase; no citable "
            "experimental density found within the timebox. Same shape as LuAl3(BO3)4: "
            "accepted, expected exclusion, not a bug.",
}


# ---------------------------------------------------------------------------
# Unit boundary -- the one place DB units become ModalFit units
# ---------------------------------------------------------------------------

def _to_modalfit_units(*, density_g_cm3=None, xray_sld_real=None, xray_sld_imag=None,
                        neutron_sld_real=None, neutron_sld_imag=None,
                        wavelength_nm=None, thickness_a=None, roughness_a=None) -> dict:
    """Single conversion boundary from materials-db units to ModalFit units.
    Every field here is currently an identity pass-through (confirmed in
    materials-db docs/modalfit_schema_notes.md Q2 -- SLD in 1e-6 A^-2, density in
    g/cm3, wavelength in nm, thickness/roughness in A, matching our DB
    exactly). Kept as an explicit function, not scattered per call site, so
    a future real mismatch has exactly one place to fix.
    """
    return dict(
        density_g_cm3=density_g_cm3,        # g/cm3 -> g/cm3 (MaterialSLD units="g / cm**3")
        xray_sld_real=xray_sld_real,        # 1e-6 A^-2 -> 1e-6 A^-2 (physics.py Q2)
        xray_sld_imag=xray_sld_imag,
        neutron_sld_real=neutron_sld_real,
        neutron_sld_imag=neutron_sld_imag,
        wavelength_nm=wavelength_nm,         # nm -> nm (nk_cauchy, nk_tabulated)
        thickness_a=thickness_a,             # A -> A (slab_model_builder.py labels, Q2)
        roughness_a=roughness_a,
    )


def _bounded(value, vmin=None, vmax=None, log_default=None):
    """dict for a ModalFit {"value","min","max"} field. Logs (via the
    returned 'used_default' flag) when we had no bound and are falling
    through to ModalFit's own auto-default rather than emitting one."""
    used_default = vmin is None and vmax is None
    if log_default and used_default:
        print(f"[modalfit export] no explicit bounds for {log_default}={value}; "
              f"ModalFit will auto-default them.")
    return {"value": value, "min": vmin, "max": vmax}


# ---------------------------------------------------------------------------
# DB lookups
# ---------------------------------------------------------------------------

def _find_material(conn, name):
    """Look up a materials row by exact name first, falling back to
    formula. Raises ExportError (does not silently pick one) if the
    formula fallback matches more than one row -- true for any formula
    with multiple genuinely distinct allotropes stored as separate
    materials rows (e.g. "C" resolves to both Diamond and Graphite,
    batch 3b). Before this check, .fetchone() on the formula query would
    silently return whichever row SQLite happened to return first for an
    ambiguous formula -- the same silent-wrong-answer shape this project
    has hunted down repeatedly elsewhere (_lookup_mp_id, material_type,
    batch 1's polymorph fallback). A caller hitting this must specify the
    exact material name instead of the formula."""
    row = conn.execute(
        "SELECT material_id, name, formula FROM materials WHERE name = ?", (name,)
    ).fetchone()
    if row is not None:
        return row

    matches = conn.execute(
        "SELECT material_id, name, formula FROM materials WHERE formula = ?", (name,)
    ).fetchall()
    if len(matches) > 1:
        names = [m[1] for m in matches]
        raise ExportError(
            f"Formula '{name}' matches {len(matches)} distinct materials: {names}. "
            f"Specify the exact material name instead of the formula to disambiguate."
        )
    return matches[0] if matches else None


# dataset_label shapes (see materials-db scripts/load_oxides_db.py and
# build_checkpoint1_report.py, which write them):
#   with polymorph:    "rutile | xray_sld_real | periodictable_CuKalpha"
#                       "rutile | Devore1951 | o-ray"
#   without polymorph: "xray_sld_real | periodictable_CuKalpha"   (physical_properties)
#                       "density_MP_DFT"                          (physical_properties, no " | " at all)
#                       "Devore1951 | o-ray"                      (optical_dispersion)
#                       "Devore1951"                              (optical_dispersion, isotropic, no axis)
# A naive split(" | ")[0] cannot tell these apart -- for a polymorph-less
# material it would treat each quantity type (or each paper) as its own
# "polymorph". Detect the absence of a polymorph segment instead by
# recognizing what the first segment looks like when one isn't there: a
# physical_properties quantity marker, or an optical "AuthorYYYY" source
# label (never a real polymorph name in this dataset -- polymorph names
# here are words like "rutile"/"wurtzite"/"K2NiF4-type", never
# Letters+4-digits).
_QUANTITY_MARKERS = ("density_", "xray_sld_real", "xray_sld_imag",
                     "neutron_sld_real", "neutron_sld_imag")
_SOURCE_LABEL_RE = re.compile(r"^[A-Za-z]+\d{4}$")


def _polymorph_prefix(dataset_label: str) -> Optional[str]:
    first = dataset_label.split(" | ", 1)[0]
    if any(first.startswith(m) for m in _QUANTITY_MARKERS) or _SOURCE_LABEL_RE.match(first):
        return None
    return first


def _density_confidence(density_dataset_label: Optional[str]) -> str:
    """DENSITY_VERIFIED or DENSITY_BULK_APPROXIMATION, read off the
    density row's own dataset_label (which already carries the
    density_source via the "density_{density_source}" convention -- see
    load_oxides_db.py's label_join()). bulk_elemental_approximation is
    the one density_source value that does NOT count as verified -- see
    process_condition.density_state_from_source() and
    materials-db docs/batch3_scoping_report.md for why this is a deliberate, argued
    distinction, not an oversight."""
    if density_dataset_label and BULK_ELEMENTAL_APPROXIMATION in density_dataset_label:
        return DENSITY_BULK_APPROXIMATION
    return DENSITY_VERIFIED


def _resolve_physical_properties(conn, material_id, material_label, dataset_label):
    rows = conn.execute(
        "SELECT dataset_label, density_g_cm3, xray_sld, neutron_sld, source_id "
        "FROM physical_properties WHERE material_id = ?",
        (material_id,),
    ).fetchall()
    if not rows:
        raise ExportError(f"'{material_label}' has no physical_properties rows at all.")

    prefixes = sorted({_polymorph_prefix(r[0]) for r in rows}, key=lambda p: (p is None, p or ""))
    if dataset_label:
        matches = [p for p in prefixes if p is not None and
                   (dataset_label == p or dataset_label.startswith(p) or p.startswith(dataset_label))]
        if not matches:
            raise ExportError(
                f"dataset_label '{dataset_label}' does not match any physical_properties "
                f"polymorph for '{material_label}'. Available: {prefixes}"
            )
        chosen_prefix = matches[0]
    else:
        if len(prefixes) > 1:
            raise ExportError(
                f"'{material_label}' has {len(prefixes)} distinct polymorphs in "
                f"physical_properties and no dataset_label was given: {prefixes}. "
                f"Specify dataset_label to disambiguate."
            )
        chosen_prefix = prefixes[0]

    selected = [r for r in rows if _polymorph_prefix(r[0]) == chosen_prefix]

    out = dict(polymorph=chosen_prefix, density_g_cm3=None, xray_sld_real=None,
               xray_sld_imag=None, neutron_sld_real=None, neutron_sld_imag=None,
               density_source_id=None, density_dataset_label=None)
    for label, density, xray, neutron, source_id in selected:
        if density is not None:
            out["density_g_cm3"] = density
            out["density_source_id"] = source_id
            out["density_dataset_label"] = label
        elif "xray_sld_real" in label:
            out["xray_sld_real"] = xray
        elif "xray_sld_imag" in label:
            out["xray_sld_imag"] = xray
        elif "neutron_sld_real" in label:
            out["neutron_sld_real"] = neutron
        elif "neutron_sld_imag" in label:
            out["neutron_sld_imag"] = neutron

    if out["density_g_cm3"] is None:
        raise ExportError(
            f"'{material_label}' (polymorph '{chosen_prefix}') has no density in "
            f"physical_properties -- refusing to export a layer with no density."
        )
    return out


def _resolve_optical_axis(conn, material_id, material_label, polymorph_prefix, dataset_label):
    """Pick ONE optical_dispersion axis. ModalFit's optical block models an
    isotropic material; a birefringent material's o/e (or biaxial
    alpha/beta/gamma) axes can't both be represented in one layer. This is
    a real simplification -- see LIMITATIONS (2) in this file's module
    docstring -- not something to hide."""
    labels = [r[0] for r in conn.execute(
        "SELECT DISTINCT dataset_label FROM optical_dispersion WHERE material_id = ?",
        (material_id,),
    ).fetchall()]
    if not labels:
        raise ExportError(f"'{material_label}' has no optical_dispersion rows at all.")

    candidates = [l for l in labels if _polymorph_prefix(l) == polymorph_prefix]
    if not candidates:
        raise ExportError(
            f"'{material_label}' has optical_dispersion data, but none under polymorph "
            f"'{polymorph_prefix}'. Available optical dataset_labels: {labels}"
        )

    if dataset_label and dataset_label in candidates:
        chosen = dataset_label
    elif len(candidates) == 1:
        chosen = candidates[0]
    else:
        # prefer an isotropic (no-axis-suffix) entry, else ordinary ray,
        # else the alphabetically-first axis -- and always report the choice.
        isotropic = [l for l in candidates if not any(s in l for s in
                     ("o-ray", "e-ray", "alpha-axis", "beta-axis", "gamma-axis"))]
        ordinary = [l for l in candidates if "o-ray" in l]
        chosen = (isotropic or ordinary or sorted(candidates))[0]
        print(f"[modalfit export] '{material_label}' has {len(candidates)} optical axes "
              f"({candidates}); no exact dataset_label given, defaulting to isotropic "
              f"approximation using '{chosen}'.")

    rows = conn.execute(
        "SELECT wavelength_nm, n, k FROM optical_dispersion "
        "WHERE material_id = ? AND dataset_label = ? ORDER BY wavelength_nm",
        (material_id, chosen),
    ).fetchall()
    source_id = conn.execute(
        "SELECT source_id FROM optical_dispersion WHERE material_id = ? AND dataset_label = ? LIMIT 1",
        (material_id, chosen),
    ).fetchone()
    return chosen, rows, (source_id[0] if source_id else None)


def _source_citation(conn, source_id):
    if source_id is None:
        return None
    row = conn.execute(
        "SELECT doi, title, authors, journal, year FROM sources WHERE source_id = ?", (source_id,)
    ).fetchone()
    if row is None:
        return None
    doi, title, authors, journal, year = row
    return dict(doi=doi, title=title, authors=authors, journal=journal, year=year)


_ANION_TO_MATERIAL_TYPE = (
    # Checked in this order: a formula containing oxygen is classified as
    # an oxide even if it also contains another anion (e.g. a borate,
    # molybdate, or vanadate -- all 50 oxide-batch formulas fit this).
    ("O", "oxide"),
    ("F", "fluoride"),
    ("N", "nitride"),
    ("S", "sulfide"),
)


def _classify_material_type(formula: str) -> str:
    """Derive the ModalFit "material_type" field from the formula's anion
    rather than a fixed string. export_layer() used to hardcode
    "material_type": "oxide" for every layer regardless of formula -- found
    during the batch-2 audit: every fluoride/nitride/sulfide layer (ZnS,
    CaF2, GaN, ...) was silently mislabeled "oxide" in its exported JSON.
    Returns "unknown" rather than guessing if none of the recognized
    anions are present (never silently mislabels)."""
    elements = set(re.findall(r"[A-Z][a-z]?", formula))
    for anion, material_type in _ANION_TO_MATERIAL_TYPE:
        if anion in elements:
            return material_type
    return "unknown"


def _lookup_mp_id(material_formula: str, enrichment_csv_dir: Optional[Path]) -> Optional[str]:
    """Best-effort enrichment: mp_id isn't a DB column (only dataset_label
    is, by the schema-freeze decision), but it IS in the per-batch enrichment
    CSVs. Globs <enrichment_csv_dir>/*.csv and checks any CSV with
    "formula"/"mp_id" columns, rather than a hardcoded filename list -- a
    hardcoded list of exactly two names ("oxides_50.csv", "batch2_28.csv")
    already caused this function to silently return None for every batch-2
    material once written, and then AGAIN, for every batch-2 AND batch-3
    material, the moment batch2_28.csv was renamed to batch2_31.csv (found
    by that rename's own test suite catching a newly-skipped test, not by
    this function failing loudly). Globbing removes the recurring failure
    mode instead of patching this instance of it. Returns None (never
    raises) if no CSV has a match -- this is supplementary provenance, not
    a required field.

    DROP-IN (3): upstream this took no directory argument and globbed
    _ROOT/"data"/*.csv. Callers now pass the directory; export_layer()
    defaults it to the database file's own parent, which IS _ROOT/"data"
    in a materials-db checkout -- so default behavior is unchanged. A
    caller with no enrichment CSVs passes None and gets None back.
    pandas is imported lazily and a missing pandas degrades to None
    rather than raising: this package's required dependencies are the
    standard library alone."""
    if enrichment_csv_dir is None:
        return None
    import glob as _glob
    try:
        import pandas as pd
    except ImportError:
        return None
    for csv_path_str in sorted(_glob.glob(str(Path(enrichment_csv_dir) / "*.csv"))):
        csv_path = Path(csv_path_str)
        try:
            df = pd.read_csv(csv_path)
            if "formula" not in df.columns or "mp_id" not in df.columns:
                continue
            match = df[df["formula"] == material_formula]
            if match.empty:
                continue
            val = match.iloc[0].get("mp_id")
            if pd.notna(val):
                return str(val)
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Sidecar n,k CSV
# ---------------------------------------------------------------------------

def _write_nk_csv(path: Path, rows) -> None:
    """physics.py's nk_tabulated() loads this with np.loadtxt(...), which
    requires every cell to parse as a float -- an empty string for a
    missing k (many of our RI.info datasets are n-only) crashes with
    'could not convert string '' to float64', not a graceful None. Write
    0.0 for missing k (a transparent/non-absorbing approximation, physically
    reasonable for the visible-range oxide data this exporter targets) and
    flag it in the returned row count so callers can see how many were
    defaulted rather than measured."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_k_defaulted = 0
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["wavelength_nm", "n", "k"])
        for wl, n, k in rows:
            if k is None:
                n_k_defaulted += 1
            w.writerow([wl, n, k if k is not None else 0.0])
    if n_k_defaulted:
        print(f"[modalfit export] {path.name}: {n_k_defaulted}/{len(rows)} rows had no "
              f"measured k, defaulted to 0.0 (transparent/non-absorbing approximation)")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_layer(db, material_name: str, dataset_label: Optional[str] = None, *,
                  thickness_a: Optional[float] = None, thickness_min: Optional[float] = None,
                  thickness_max: Optional[float] = None,
                  roughness_a: Optional[float] = None, roughness_min: Optional[float] = None,
                  roughness_max: Optional[float] = None,
                  nk_csv_dir: Path = Path("."), role: str = "layer",
                  label: Optional[str] = None,
                  enrichment_csv_dir: Optional[Path] = None) -> dict:
    """Build one ModalFit layer dict from the materials database, writing
    its sidecar n,k CSV into nk_csv_dir. Raises ExportError rather than
    emitting a null for a missing density, an ambiguous dataset_label with
    no way to pick one, or missing optical data.

    Two conventions this layer's "structural.roughness" and
    "xray.sld_imag"/"neutron.sld_imag" fields commit to, verified directly
    against ModalFit's fitting code (physics.py's _make_xrr_slab/
    _make_xrr_boundary and refnx's Scatterer/MaterialSLD, not just against
    our own simulator) rather than assumed from how they parse -- see
    materials-db docs/xrr_fit_findings.md for the verification:

    1. roughness_a describes the interface ABOVE this layer (between the
       previous entry in the stack and this one), never below. This is
       refnx's own Scatterer convention (`sld_obj(thick, rough)`) --
       ModalFit's _make_xrr_slab/_make_xrr_boundary call it exactly that
       way, reading `rough` straight off THIS entry. Get this backwards
       (as src/materials_db/simulation/xrr.py's parratt() did until this
       was checked) and every interface's roughness silently attaches to
       the wrong side, with no error.
    2. A positive imaginary SLD means absorption (this repo's stored
       convention throughout: periodictable's xray_sld(), this DB's
       xray_sld_imag column, this field). Both of ModalFit's actual
       consumption paths agree with that sign as-is: refnx.reflect.SLD
       correctly treats a positive imaginary part as absorptive with no
       conjugation needed, and the DEFAULT path (MaterialSLD, used
       whenever molecular.formula + molecular.density are both present --
       i.e. every layer this exporter emits) recomputes SLD independently
       from refnx's own tables and agrees with this DB's periodictable
       value to 5 significant figures, confirming the two are consistent
       rather than one silently overriding the other with a different
       sign.
    """
    conn = sqlite3.connect(str(db)) if isinstance(db, (str, Path)) else db
    close_after = isinstance(db, (str, Path))
    try:
        mat_row = _find_material(conn, material_name)
        if mat_row is None:
            raise ExportError(f"Material '{material_name}' not found in {db}")
        material_id, db_name, formula = mat_row

        phys = _resolve_physical_properties(conn, material_id, material_name, dataset_label)
        opt_label, nk_rows, opt_source_id = _resolve_optical_axis(conn, material_id, material_name,
                                                                    phys["polymorph"], dataset_label)

        u = _to_modalfit_units(
            density_g_cm3=phys["density_g_cm3"],
            xray_sld_real=phys["xray_sld_real"], xray_sld_imag=phys["xray_sld_imag"],
            neutron_sld_real=phys["neutron_sld_real"], neutron_sld_imag=phys["neutron_sld_imag"],
            thickness_a=thickness_a, roughness_a=roughness_a,
        )

        label = label or (f"{formula}_{phys['polymorph']}" if phys["polymorph"] else formula)
        # Sanitize the label into a flat, filesystem-safe filename -- a
        # bare .replace(" ", "_") missed "/", which two real polymorph
        # names contain ("corundum/sapphire", "scheelite/wulfenite").
        # Found live: export_stack() picking Sapphire as a substrate wrote
        # "Al2O3_corundum/sapphire_nk.csv" as the optical.params.file
        # value, which os.path.join'd into an ACCIDENTAL nested
        # subdirectory ("Al2O3_corundum/" containing "sapphire_nk.csv")
        # instead of the flat file in nk_csv_dir this function's own
        # docstring promises. It happened to still resolve (ModalFit's
        # _resolve_nk_path does the same os.path.join), so nothing ever
        # crashed -- but it's an accident, not a design, and a second
        # slash-containing label sharing the same prefix could collide in
        # ways the label-disambiguation logic never accounts for (it
        # tracks the full label string, not the sanitized filename). Same
        # sanitizer as export_all_materials_modalfit.py's _safe_dirname().
        nk_filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", label) + "_nk.csv"
        _write_nk_csv(Path(nk_csv_dir) / nk_filename, nk_rows)

        density_citation = _source_citation(conn, phys["density_source_id"])
        optical_citation = _source_citation(conn, opt_source_id)
        resolved = RESOLVED_OPTICAL_SOURCE_CITATION.get(formula)
        if optical_citation is not None and resolved is not None:
            optical_citation = dict(optical_citation, verification_note=resolved["verification_note"])
        # DROP-IN (3): default the enrichment-CSV search to the database's
        # own directory -- data/ in a materials-db checkout, where the
        # per-batch CSVs sit beside materials_oxide_test.db.
        if enrichment_csv_dir is None and isinstance(db, (str, Path)):
            enrichment_csv_dir = Path(db).parent
        mp_id = _lookup_mp_id(formula, enrichment_csv_dir)

        density_confidence = _density_confidence(phys["density_dataset_label"])
        density_bounds = (bulk_approximation_density_bounds(u["density_g_cm3"])
                          if density_confidence == DENSITY_BULK_APPROXIMATION
                          else verified_density_bounds(u["density_g_cm3"]))

        layer = {
            "label": label,
            "role": role,
            "material_type": _classify_material_type(formula),
            "molecular": {"formula": formula, "density_g_cm3": u["density_g_cm3"],
                          "density_confidence": density_confidence,
                          "density_bounds": density_bounds},
            "structural": {
                "thickness": _bounded(u["thickness_a"], thickness_min, thickness_max,
                                      log_default=f"{label}.thickness" if u["thickness_a"] is not None else None),
                "roughness": _bounded(u["roughness_a"], roughness_min, roughness_max,
                                      log_default=f"{label}.roughness" if u["roughness_a"] is not None else None),
            },
            "optical": {"model": "Tabulated n,k", "params": {"file": nk_filename}},
            "xray": {
                "sld_real": {"value": u["xray_sld_real"], "min": None, "max": None},
                "sld_imag": {"value": u["xray_sld_imag"], "min": None, "max": None},
            },
            "neutron": {
                "sld_real": {"value": u["neutron_sld_real"], "min": None, "max": None},
                "sld_imag": {"value": u["neutron_sld_imag"], "min": None, "max": None},
            },
            # alias for the standalone model_predictor.py tool, which reads
            # "scattering" instead of "xray"/"neutron" -- see schema notes.
            "scattering": {
                "sld_real": {"value": u["xray_sld_real"], "min": None, "max": None},
                "sld_imag": {"value": u["xray_sld_imag"], "min": None, "max": None},
            },
            "materials_db": {
                "dataset_label": phys["density_dataset_label"],
                "optical_dataset_label": opt_label,
                "mp_id": mp_id,
                "density_confidence": density_confidence,
                "density_source": density_citation,
                "optical_source": optical_citation,
            },
        }
        return layer
    finally:
        if close_after:
            conn.close()


def export_stack(db, layers: list, *, ambient="air", substrate: str = "Silicon",
                  substrate_dataset_label: Optional[str] = None,
                  substrate_roughness_a: Optional[float] = None,
                  substrate_roughness_min: Optional[float] = None,
                  substrate_roughness_max: Optional[float] = None,
                  stack_id: Optional[str] = None, sample_id: Optional[str] = None,
                  out_dir: Path = Path("."),
                  enrichment_csv_dir: Optional[Path] = None) -> dict:
    """Assemble a full ModalFit stack: ambient + film layers + substrate.

    substrate is DB-driven, exactly like a film layer -- pass any
    materials_oxide_test.db name or formula (default "Silicon", the pure
    element added in batch 3; previously a fixed, non-DB-sourced Si
    placeholder). Resolved via export_layer(role="substrate") internally,
    so a substrate carries the SAME density_confidence/density_bounds/
    citation fields a film layer does -- the old placeholder had none of
    that (no way to see whether the substrate's density was trustworthy,
    because it wasn't a DB lookup at all). `substrate_dataset_label`
    disambiguates a substrate material with more than one polymorph, same
    as a film layer's `dataset_label`. Raises ExportError if the substrate
    name/formula isn't found in `db` -- same "raise, don't guess" contract
    export_layer() already has for a film layer.

    ambient accepts either the literal string "air" (default, an exact-
    zero-SLD placeholder -- materials_oxide_test.db has no liquid/gas
    materials, so there is nothing to look up) or a pre-built ambient
    entry dict, e.g. from materials_db.launcher.ambient.build_ambient_entry
    ("vacuum"/"d2o"/"h2o") -- checked against ModalFit's actual ambient-
    handling code (physics.py:_make_xrr_boundary, compute_se) before that
    module was written; see its docstring for what's confirmed and what's
    a labeled approximation.

    substrate_roughness_a matters more than it looks: ModalFit's
    _make_xrr_boundary() reads the film/substrate interface roughness from
    the SUBSTRATE entry's own "structural.roughness", not from the last
    film layer's. export_layer() always keeps this field PRESENT with
    value=None when no roughness is given (same convention as a film
    layer's thickness_a/roughness_a, and the same "no explicit bounds"
    notice _bounded() prints for one) rather than omitting the key --
    before this parameter existed at all, the old hardcoded substrate had
    no "structural" key whatsoever, so roughness silently read back as 0.0
    (a perfectly sharp interface) with no error (see materials-db
    docs/xrr_fit_findings.md).
    Pass a real value for any stack meant to be fit against real
    reflectivity data.

    Layer labels (film AND substrate) are disambiguated BEFORE any layer
    is exported: the substrate's label is resolved first and seeded into
    the collision-tracking, so a film layer that happens to land on the
    SAME label the substrate resolved to (e.g. "Silicon" chosen as both a
    thin film AND the substrate -- unusual, but not physically
    meaningless, and the schema doesn't forbid it) gets a "#2" suffix
    rather than colliding with the substrate's own sidecar n,k CSV.
    Among film layers, two that would resolve to the same label (the same
    formula+polymorph, or two layers explicitly given the same `label`)
    get a "#2", "#3", ... suffix appended to every occurrence after the
    first. Without this, a repeated-unit stack (a Bragg mirror, a
    superlattice -- a real sample type, not a contrived one) would
    silently produce two layers with the IDENTICAL label: their sidecar
    n,k CSVs would collide in nk_csv_dir (the second write overwriting the
    first), and worse, physics.extract_params() builds each fittable
    parameter's key as f"{label}:thick" etc., so both layers would get the
    SAME key -- found by reproducing it directly (a SiO2/Ta2O5/SiO2 stack
    produced two ParamSpecs both keyed "SiO2_amorphous:thick"), meaning
    FitEngine could not move the two physically distinct layers
    independently. See materials-db docs/xrr_fit_findings.md."""
    out_dir = Path(out_dir)

    if isinstance(ambient, dict):
        ambient_entry = dict(ambient)
    elif isinstance(ambient, str) and ambient.lower() == "air":
        ambient_entry = {"label": "Air", "role": "ambient", "material_type": "ambient",
                          "xray": {"sld_real": {"value": 0.0}, "sld_imag": {"value": 0.0}},
                          "neutron": {"sld_real": {"value": 0.0}, "sld_imag": {"value": 0.0}}}
    else:
        raise ExportError(
            f"Unknown ambient {ambient!r} -- materials_oxide_test.db has no liquid/gas "
            f"materials, so ambient isn't DB-driven. Pass 'air' (default) or a pre-built "
            f"entry dict, e.g. materials_db.launcher.ambient.build_ambient_entry('vacuum'/"
            f"'d2o'/'h2o')."
        )

    # DROP-IN (3): resolve once here, before the connection is opened --
    # export_layer() is called below with an open Connection, from which a
    # database directory can no longer be derived.
    if enrichment_csv_dir is None and isinstance(db, (str, Path)):
        enrichment_csv_dir = Path(db).parent

    conn = sqlite3.connect(str(db)) if isinstance(db, (str, Path)) else db
    close_after = isinstance(db, (str, Path))
    try:
        # Resolve the substrate's label FIRST -- it's exempt from its own
        # "#N" suffix (there is exactly one substrate) but seeds
        # seen_counts below so a colliding FILM layer is the one that
        # gets disambiguated.
        sub_mat_row = _find_material(conn, substrate)
        if sub_mat_row is None:
            raise ExportError(f"Substrate material '{substrate}' not found in {db}")
        _sub_material_id, _sub_db_name, sub_formula = sub_mat_row
        sub_phys = _resolve_physical_properties(conn, _sub_material_id, substrate, substrate_dataset_label)
        substrate_label = f"{sub_formula}_{sub_phys['polymorph']}" if sub_phys["polymorph"] else sub_formula

        # Resolve every FILM layer's label next, using the exact same
        # default export_layer() would compute (formula_polymorph, or bare
        # formula with no polymorph) -- reusing its own resolution helpers
        # rather than re-deriving the rule, so this can never silently
        # diverge from what export_layer() would have picked on its own.
        # Then disambiguate any collision (whether from two identical
        # caller-supplied labels, two layers landing on the same default,
        # or a collision with the substrate's own label) before a single
        # export_layer() call runs, so no sidecar CSV is ever written
        # under a name a later layer (or the substrate) will overwrite.
        final_labels = []
        seen_counts: dict = {substrate_label: 1}
        for spec in layers:
            mat_row = _find_material(conn, spec["material"])
            if mat_row is None:
                raise ExportError(f"Material '{spec['material']}' not found in {db}")
            material_id, _db_name, formula = mat_row
            if spec.get("label"):
                base_label = spec["label"]
            else:
                phys = _resolve_physical_properties(conn, material_id, spec["material"], spec.get("dataset_label"))
                base_label = f"{formula}_{phys['polymorph']}" if phys["polymorph"] else formula
            seen_counts[base_label] = seen_counts.get(base_label, 0) + 1
            occurrence = seen_counts[base_label]
            final_labels.append(base_label if occurrence == 1 else f"{base_label}#{occurrence}")

        stack_layers = []
        for spec, final_label in zip(layers, final_labels):
            stack_layers.append(export_layer(
                conn, spec["material"], spec.get("dataset_label"),
                thickness_a=spec.get("thickness_a"), thickness_min=spec.get("thickness_min"),
                thickness_max=spec.get("thickness_max"),
                roughness_a=spec.get("roughness_a"), roughness_min=spec.get("roughness_min"),
                roughness_max=spec.get("roughness_max"),
                nk_csv_dir=out_dir, role="layer", label=final_label,
                enrichment_csv_dir=enrichment_csv_dir,
            ))

        substrate_entry = export_layer(
            conn, substrate, substrate_dataset_label,
            roughness_a=substrate_roughness_a, roughness_min=substrate_roughness_min,
            roughness_max=substrate_roughness_max,
            nk_csv_dir=out_dir, role="substrate", label=substrate_label,
            enrichment_csv_dir=enrichment_csv_dir,
        )
        substrate_entry["materials_db"]["note"] = (
            f"DB-sourced substrate ('{substrate}') -- see this entry's own "
            f"density_confidence/density_source above, same as any film layer."
        )
    finally:
        if close_after:
            conn.close()

    stack = [ambient_entry] + stack_layers + [substrate_entry]
    return {
        "stack_id": stack_id or "materials_db_export",
        "sample_id": sample_id or "materials_db_export",
        "version": 1,
        "provenance": {"generated_by": "modalfit_db_export.exporter", "source_db": str(db)},
        "n_layers": len(stack_layers),
        "stack": stack,
    }


# ==========================================================================
# SECTION 5 -- WRITING JSON TO DISK
# ==========================================================================
# The "point it at a .db and a directory" entry points.
#
# One deliberate behavior change from materials-db's own bulk script
# (scripts/export_all_materials_modalfit.py), called out because it is a
# change and not a port: that script discovers which materials to export by
# globbing data/*.csv for the per-batch enrichment files and asserting the
# count matches the DB's own. Here the DATABASE IS THE SOURCE OF TRUTH
# (SELECT name, formula FROM materials), because a drop-in cannot assume
# those CSVs travelled with it. The resulting material set is identical
# whenever both are available -- that script asserts as much -- and this
# version also works on a database standing on its own. Pass strict=True to
# keep the upstream assertion that the skip set matches KNOWN_EXCLUSIONS.

def _safe_dirname(name: str) -> str:
    """Filesystem-safe directory name derived from a material's `name`
    (the schema's real UNIQUE identity key), not its formula. Formula
    cannot be used as the export key: Diamond and Graphite genuinely
    share formula "C" -- two distinct, optically unrelated materials, the
    same ambiguity exporter._find_material() raises ExportError on rather
    than silently resolving."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


def list_materials(db_path) -> list:
    """Every selectable material in the database: [{material_id, name,
    formula}, ...] ordered by name. `name` is what to pass as a layer's
    "material" -- it is the schema's UNIQUE key, whereas formula is not."""
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT material_id, name, formula FROM materials ORDER BY name"
        ).fetchall()
    finally:
        conn.close()
    return [dict(material_id=r[0], name=r[1], formula=r[2]) for r in rows]


def export_stack_json(db_path, out_dir, layers: list, *,
                      ambient="air", substrate: str = "Silicon",
                      substrate_dataset_label: Optional[str] = None,
                      substrate_roughness_a: Optional[float] = None,
                      substrate_roughness_min: Optional[float] = None,
                      substrate_roughness_max: Optional[float] = None,
                      stack_id: Optional[str] = None,
                      sample_id: Optional[str] = None,
                      filename: str = "stack.json") -> Path:
    """Connect to `db_path`, build ambient + `layers` + substrate, and
    write the ModalFit slab-model JSON into `out_dir` alongside the
    sidecar n,k CSVs it references. Returns the JSON's path.

    `layers` is a list of dicts, outermost film first:
        {"material": "TiO2",            # DB name (preferred) or formula
         "dataset_label": "rutile",     # required only for a multi-polymorph material
         "thickness_a": 500.0,          # Angstrom
         "roughness_a": 5.0,            # Angstrom, interface ABOVE this layer
         "thickness_min"/"thickness_max"/"roughness_min"/"roughness_max": fit bounds,
         "label": "..."}                # optional; defaults to formula_polymorph

    The JSON and its CSVs MUST stay in the same directory: each layer's
    optical.params.file is a bare filename resolved relative to the JSON.
    Moving the JSON alone silently breaks every tabulated-n,k layer.

    Raises ExportError rather than emitting a null for a missing density,
    an unresolvable dataset_label, or missing optical data.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stack = export_stack(
        str(db_path), layers,
        ambient=ambient, substrate=substrate,
        substrate_dataset_label=substrate_dataset_label,
        substrate_roughness_a=substrate_roughness_a,
        substrate_roughness_min=substrate_roughness_min,
        substrate_roughness_max=substrate_roughness_max,
        stack_id=stack_id, sample_id=sample_id,
        out_dir=out_dir,
    )

    json_path = out_dir / filename
    json_path.write_text(json.dumps(stack, indent=2))
    return json_path


def export_all_layers(db_path, out_dir, *, strict: bool = False) -> dict:
    """Export EVERY material in `db_path` as its own single-layer ModalFit
    JSON: out_dir/<Material_Name>/<Material_Name>_layer.json, each beside
    its own sidecar n,k CSV. Writes an export_report.csv summarising every
    material's outcome. Returns
    {"n_ok", "n_skipped", "n_total", "out_dir", "report_path", "results"}.

    A material that legitimately cannot be exported (no citable density,
    no optical data) is recorded as SKIPPED with its ExportError message
    rather than failing the run -- see KNOWN_EXCLUSIONS.

    strict=True additionally asserts the skip set matches KNOWN_EXCLUSIONS
    exactly, so that BOTH a new failure (a regression) and a material that
    unexpectedly starts succeeding (its underlying gap got fixed, and
    KNOWN_EXCLUSIONS is now stale) raise instead of passing silently. Use
    it in CI against the materials-db database; leave it off when pointing
    this at a different or partial database, where the expected skip set
    is by definition different.

    out_dir is wiped and recreated each run rather than mkdir-if-missing:
    a stale directory from a prior naming scheme can silently collide on a
    case-insensitive filesystem with a directory this run creates (this
    happened once upstream -- a leftover formula-keyed "TiN/" collided
    with a name-keyed "Tin/" and got overwritten). A full rebuild makes
    that class of collision structurally impossible, not merely unlikely.
    """
    db_path = Path(db_path)
    out_dir = Path(out_dir)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    materials = list_materials(db_path)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for mat in materials:
        name, formula = mat["name"], mat["formula"]
        dirname = _safe_dirname(name)
        mat_dir = out_dir / dirname
        try:
            # Look up by `name`, not `formula`: name is the schema's real
            # UNIQUE key, and passing a formula shared by several materials
            # (e.g. "C") would hit _find_material's ambiguity ExportError
            # for every such material, not only the genuinely ambiguous ones.
            layer = export_layer(str(db_path), name, nk_csv_dir=mat_dir, label=name)
            mat_dir.mkdir(parents=True, exist_ok=True)
            layer_path = mat_dir / f"{dirname}_layer.json"
            layer_path.write_text(json.dumps(layer, indent=2))
            results.append(dict(
                formula=formula, name=name, status="OK",
                dataset_label=layer["materials_db"]["dataset_label"],
                optical_dataset_label=layer["materials_db"]["optical_dataset_label"],
                density_confidence=layer["materials_db"]["density_confidence"],
                xray_sld_real=layer["xray"]["sld_real"]["value"],
                path=str(layer_path), error=None,
            ))
        except ExportError as e:
            results.append(dict(
                formula=formula, name=name, status="SKIPPED",
                dataset_label=None, optical_dataset_label=None,
                density_confidence=None, xray_sld_real=None,
                path=None, error=str(e),
            ))

    report_path = out_dir / "export_report.csv"
    fields = ["formula", "name", "status", "dataset_label", "optical_dataset_label",
              "density_confidence", "xray_sld_real", "path", "error"]
    with open(report_path, "w", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)

    n_ok = sum(1 for r in results if r["status"] == "OK")
    n_skipped = sum(1 for r in results if r["status"] == "SKIPPED")

    if strict:
        actual_skips = {r["formula"] for r in results if r["status"] == "SKIPPED"}
        expected_skips = set(KNOWN_EXCLUSIONS)
        unexpected = actual_skips - expected_skips
        if unexpected:
            raise AssertionError(
                f"Export failed for material(s) not in KNOWN_EXCLUSIONS: {sorted(unexpected)}. "
                f"This is a regression, not an expected exclusion -- investigate before proceeding."
            )
        newly_succeeding = expected_skips - actual_skips
        if newly_succeeding:
            raise AssertionError(
                f"Material(s) previously in KNOWN_EXCLUSIONS now export successfully: "
                f"{sorted(newly_succeeding)}. If their underlying gap was genuinely fixed, "
                f"update KNOWN_EXCLUSIONS (SECTION 4) to reflect it -- don't let this "
                f"pass silently."
            )

    return dict(n_ok=n_ok, n_skipped=n_skipped, n_total=len(materials),
                out_dir=out_dir, report_path=report_path, results=results)


# ==========================================================================
# SECTION 6 -- COMMAND LINE INTERFACE
# ==========================================================================
# python3 modalfit_export.py --db <database.db> --out <dir> [options]
#
# Three modes, all taking the same --db / --out pair:
#
#   --list                 print every material in the database and exit
#   (default)              export EVERY material as its own layer JSON
#   --layer SPEC [SPEC..]  build ONE stack from the given layers
#
# A layer SPEC is  MATERIAL[@POLYMORPH][:THICKNESS_A[:ROUGHNESS_A]]  e.g.
#     TiO2@rutile:500:5      SiO2:1000      Gold:200
# Outermost film first; ambient and substrate are added automatically.

def _parse_layer_spec(spec: str) -> dict:
    """MATERIAL[@POLYMORPH][:THICKNESS_A[:ROUGHNESS_A]] -> layer dict.

    Splits on '@' BEFORE ':' so a polymorph containing neither is safe,
    and rejects a non-numeric thickness/roughness loudly instead of
    letting float() raise a bare ValueError with no context about which
    spec was malformed."""
    parts = spec.split(":")
    material = parts[0]
    dataset_label = None
    if "@" in material:
        material, dataset_label = material.split("@", 1)
        dataset_label = dataset_label or None
    if not material:
        raise argparse.ArgumentTypeError(f"Layer spec {spec!r} has no material name.")

    layer = {"material": material}
    if dataset_label:
        layer["dataset_label"] = dataset_label
    for index, key in ((1, "thickness_a"), (2, "roughness_a")):
        if len(parts) > index and parts[index] != "":
            try:
                layer[key] = float(parts[index])
            except ValueError:
                raise argparse.ArgumentTypeError(
                    f"Layer spec {spec!r}: {key} must be a number in Angstrom, "
                    f"got {parts[index]!r}."
                )
    if len(parts) > 3:
        raise argparse.ArgumentTypeError(
            f"Layer spec {spec!r} has too many ':' fields -- expected "
            f"MATERIAL[@POLYMORPH][:THICKNESS_A[:ROUGHNESS_A]]."
        )
    return layer


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m modalfit_db_export",
        description="Export materials-db SQLite content as ModalFit slab-model JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--db", required=True, type=Path,
                   help="Path to the materials SQLite database.")
    p.add_argument("--out", type=Path,
                   help="Output directory (required unless --list).")
    p.add_argument("--list", action="store_true",
                   help="List every material in the database and exit.")
    p.add_argument("--layer", nargs="+", metavar="SPEC",
                   help="Build one stack from these layers, outermost first: "
                        "MATERIAL[@POLYMORPH][:THICKNESS_A[:ROUGHNESS_A]]")
    p.add_argument("--substrate", default="Silicon",
                   help="Substrate material name or formula (default: Silicon).")
    p.add_argument("--substrate-polymorph", default=None,
                   help="dataset_label disambiguating a multi-polymorph substrate.")
    p.add_argument("--substrate-roughness", type=float, default=None, metavar="ANGSTROM",
                   help="Film/substrate interface roughness. ModalFit reads this from "
                        "the SUBSTRATE entry, not the last film -- omitting it leaves a "
                        "perfectly sharp interface. Set it for any stack meant to be fit "
                        "against real reflectivity data.")
    p.add_argument("--ambient", default="air", choices=["air"],
                   help="Ambient medium (default: air). Non-air ambients are not "
                        "DB-sourced -- pass a pre-built entry dict via the Python API.")
    p.add_argument("--stack-id", default=None, help="stack_id written into the JSON.")
    p.add_argument("--sample-id", default=None, help="sample_id written into the JSON.")
    p.add_argument("--filename", default="stack.json",
                   help="Stack JSON filename inside --out (default: stack.json).")
    p.add_argument("--strict", action="store_true",
                   help="Whole-catalog mode: assert the skip set matches KNOWN_EXCLUSIONS "
                        "exactly. Use against the materials-db database in CI.")
    args = p.parse_args(argv)

    if not args.db.exists():
        p.error(f"Database not found: {args.db}")

    if args.list:
        materials = list_materials(args.db)
        for m in materials:
            print(f"{m['name']:<40} {m['formula']}")
        print(f"\n{len(materials)} materials in {args.db}")
        return 0

    if args.out is None:
        p.error("--out is required unless --list is given.")

    if args.layer:
        try:
            layers = [_parse_layer_spec(s) for s in args.layer]
        except argparse.ArgumentTypeError as e:
            p.error(str(e))
        try:
            json_path = export_stack_json(
                args.db, args.out, layers,
                ambient=args.ambient, substrate=args.substrate,
                substrate_dataset_label=args.substrate_polymorph,
                substrate_roughness_a=args.substrate_roughness,
                stack_id=args.stack_id, sample_id=args.sample_id,
                filename=args.filename,
            )
        except ExportError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"Wrote {json_path}")
        print(f"Sidecar n,k CSVs are in {args.out} -- keep them beside the JSON.")
        return 0

    summary = export_all_layers(args.db, args.out, strict=args.strict)
    print(f"Exported {summary['n_ok']}/{summary['n_total']} materials, "
          f"{summary['n_skipped']} skipped.")
    print(f"Report: {summary['report_path']}")
    if summary["n_skipped"]:
        print("\nSkipped:")
        for r in summary["results"]:
            if r["status"] == "SKIPPED":
                print(f"  {r['name']} ({r['formula']}): {r['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
