"""launcher/ambient.py
======================
Ambient-medium presets for the ModalFit launcher: air (default), vacuum,
D2O, H2O.

These are explicitly NOT DB-sourced -- materials_oxide_test.db has zero
liquid/gas materials (it's a thin-film oxide/element/etc. database), so
there is nothing to select from for "ambient" the way there is for a film
or substrate. This module is a small, clearly-labeled, literature-cited
constant table, the same honest treatment export_stack() already gave the
old hardcoded Silicon substrate placeholder before this launcher made
substrate DB-driven (see export/modalfit.py) -- never pretend a fixed
constant is a verified DB value.

Checked against ModalFit's schema before building this (physics.py,
pinned commit 4eef754295be929f77b04dcfcd8b6c882ba5f101):

- _make_xrr_boundary()'s ambient branch (physics.py:386-397) accepts EITHER
  molecular.formula + molecular.density (computed live via refnx's
  MaterialSLD, the exact same path every DB layer already uses) OR a raw
  xray/neutron sld_real value. Air/vacuum have no real chemical formula
  refnx recognizes (confirmed empirically: MaterialSLD("Air", ...) raises
  "unknown element Ai") -- they get the raw-SLD path (both ~0, see below).
  D2O/H2O get the molecular path, since "D2O"/"H2O" ARE real formulas
  refnx and periodictable parse correctly (deuterium recognized as its own
  element, confirmed empirically -- see the neutron_sld values below,
  which match the standard reflectometry-textbook values for D2O/H2O to
  3 significant figures).
- compute_se()/_make_refellips_ri() (physics.py:238-266, 267-297) ALSO
  reads the ambient entry's own "optical" block for ellipsometry -- an
  ambient with no "optical" key at all silently defaults to model="scalar",
  n=1.0, k=0.0 (physics.py:216-234's get_nk()/_make_refellips_ri()
  fallback). That default is an excellent approximation for air/vacuum
  (correct to 4 decimal places) but is explicitly wrong for a liquid
  ambient -- so D2O/H2O get a real, cited scalar index instead of
  silently inheriting the vacuum default.

SLD precomputation: xray_sld_real/imag and neutron_sld_real/imag for D2O/
H2O below are computed via `periodictable` at THIS repo's own established
convention (XRAY_ENERGY_KEV=8.048, NEUTRON_WAVELENGTH_A=1.798 -- the same
constants build_oxides_csv.py's compute_sld() uses for every DB material),
not guessed or pulled from a differently-conventioned source. Verified
empirically against refnx.reflect.MaterialSLD directly (which internally
uses periodictable too) -- the two agree to 10+ significant figures for
both D2O and H2O, and both match the standard reflectometry-textbook
values (H2O neutron SLD -0.56e-6 A^-2, D2O +6.35e-6 A^-2; see e.g. Cousin
& Fadda, "An Introduction to Neutron Reflectometry", EPJ Web Conf. 2020).
These precomputed values are written into the exported JSON as a
redundant-but-safe fallback (same "molecular AND xray/neutron both
present" convention export_layer() already uses) -- ModalFit's own
MaterialSLD path is what actually runs at fit time whenever
use_material_sld=True (the default), so this is a display/fallback value,
not the authoritative one.

Optical index for D2O/H2O is a CONSTANT scalar approximation (the sodium
D-line value, ~589nm), not a real dispersion curve -- unlike every DB
material, water's tabulated n,k is not wired into this exporter (RI.info
does have real H2O/D2O dispersion data under its "main/H2O" book, but
pulling it in would mean adding water to materials_oxide_test.db as a
real, enriched, cited material -- a new batch of its own, out of scope for
this launcher). Flagged explicitly in each preset's `note`, not silently
presented as equivalent to a DB material's real dispersion data.
"""

from typing import Optional

AMBIENT_PRESETS = {
    "air": dict(
        label="Air",
        molecular=None,
        xray_sld_real=0.0, xray_sld_imag=0.0,
        neutron_sld_real=0.0, neutron_sld_imag=0.0,
        optical_n=1.0, optical_k=0.0,
        note=(
            "NOT a DB material -- air and vacuum are numerically identical in this "
            "convention. Real air's SLD (~2.6e-4 in 1e-6 A^-2 units, from N2/O2's own "
            "electron/nuclear density) is ~10,000x smaller than any solid/liquid layer "
            "in this database and is not modeled. refnx has no 'Air' formula at all "
            "(confirmed: MaterialSLD('Air', ...) raises 'unknown element Ai')."
        ),
    ),
    "vacuum": dict(
        label="Vacuum",
        molecular=None,
        xray_sld_real=0.0, xray_sld_imag=0.0,
        neutron_sld_real=0.0, neutron_sld_imag=0.0,
        optical_n=1.0, optical_k=0.0,
        note=(
            "NOT a DB material -- exact zero SLD and n=1.0/k=0.0 by definition, "
            "identical to this launcher's 'air' preset at this SLD/index precision "
            "(see 'air' preset's note for why the two are not distinguished here)."
        ),
    ),
    "d2o": dict(
        label="D2O (heavy water)",
        molecular=dict(formula="D2O", density_g_cm3=1.107),
        # periodictable.formula("D2O", density=1.107).xray_sld(energy=8.048) /
        # .neutron_sld(wavelength=1.798) -- matches refnx.MaterialSLD("D2O", 1.107,
        # probe=...) to 10+ significant figures (verified empirically).
        xray_sld_real=9.4292, xray_sld_imag=0.031618,
        neutron_sld_real=6.3712, neutron_sld_imag=0.0,
        optical_n=1.328, optical_k=0.0,  # literature value at ~589nm (Na D-line)
        note=(
            "NOT a DB material -- materials_oxide_test.db has no liquid/gas entries. "
            "SLD is computed live by ModalFit via molecular.formula+density (the same "
            "refnx MaterialSLD path every DB layer already uses); the xray/neutron "
            "values above are a precomputed, verified-consistent fallback, not the "
            "authoritative source. Optical index (1.328) is a CONSTANT approximation "
            "at the sodium D-line, not a real dispersion curve -- RI.info has tabulated "
            "D2O data (main/H2O/nk/Kedenburg.yml), but wiring it in would mean adding "
            "water to the DB as a real enriched material, out of scope here."
        ),
    ),
    "h2o": dict(
        label="H2O (light water)",
        molecular=dict(formula="H2O", density_g_cm3=0.997),
        xray_sld_real=9.4408, xray_sld_imag=0.031657,
        neutron_sld_real=-0.5593, neutron_sld_imag=0.0,
        optical_n=1.333, optical_k=0.0,  # literature value at ~589nm (Na D-line)
        note=(
            "NOT a DB material -- see the 'd2o' preset's note (same caveats apply: "
            "SLD computed live via molecular.formula+density, precomputed values here "
            "are a verified-consistent fallback; optical index is a constant "
            "approximation, not a real dispersion curve)."
        ),
    ),
}


def build_ambient_entry(preset_name: str) -> dict:
    """Build the ModalFit ambient stack-entry dict for a named preset.
    Raises ValueError (not KeyError) on an unrecognized name, listing the
    real options -- same "raise, don't guess" discipline as
    format_process_condition()."""
    key = preset_name.lower()
    if key not in AMBIENT_PRESETS:
        raise ValueError(
            f"Unrecognized ambient preset {preset_name!r}. Available: "
            f"{sorted(AMBIENT_PRESETS)}."
        )
    p = AMBIENT_PRESETS[key]
    entry = {
        "label": p["label"],
        "role": "ambient",
        "material_type": "ambient",
        "optical": {"model": "scalar", "params": {"n": p["optical_n"], "k": p["optical_k"]}},
        "xray": {"sld_real": {"value": p["xray_sld_real"]}, "sld_imag": {"value": p["xray_sld_imag"]}},
        "neutron": {"sld_real": {"value": p["neutron_sld_real"]}, "sld_imag": {"value": p["neutron_sld_imag"]}},
        "scattering": {"sld_real": {"value": p["xray_sld_real"]}, "sld_imag": {"value": p["xray_sld_imag"]}},
        "materials_db": {"note": p["note"], "preset": key},
    }
    if p["molecular"] is not None:
        entry["molecular"] = dict(p["molecular"])
    return entry


def describe_ambient_presets() -> list:
    """List (name, label, one-line-summary) for every preset -- what the
    launcher CLI shows when prompting for an ambient choice."""
    return [(name, p["label"], p["note"].split(" -- ")[0]) for name, p in AMBIENT_PRESETS.items()]
