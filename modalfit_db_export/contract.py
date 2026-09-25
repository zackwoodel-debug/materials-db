#!/usr/bin/env python3
"""
contract.py
===========
Pinned ModalFit version this exporter's schema assumptions were verified
against, plus the specific findings with file:line citations they rest on.

Why this exists as code, not just a README note: ModalFit's OWN README has
already diverged from its actual behavior twice during this integration --
it documents an `examples/` directory that does not exist anywhere in the
repository, and labels SLD units inconsistently between the GUI's
LayerEditor ("x1e-6 A^-2") and SubstrateEditor ("A^-2") for functionally
identical fields. Upstream docs and upstream behavior have already
diverged once; if optical.params.file resolution (or any of the other
confirmed behaviors below) ever misbehaves, the first move is to diff a
fresh ModalFit clone against MODALFIT_COMMIT_SHA and re-check the cited
lines -- that tells you immediately whether it's a materials-db bug or
upstream drift, instead of re-deriving the whole schema from scratch.

Use verify_pin.py (materials-db scripts/verify_modalfit_pin.py) to check a clone's
current commit against the pin below.
"""

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
