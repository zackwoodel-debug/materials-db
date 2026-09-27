#!/usr/bin/env python3
"""
scripts/gas_material_list.py
============================
The gas family: permanent gases, the heavier rare gases (with their liquid and solid phases at cryogenic temperatures), light
hydrocarbons and air, from refractiveindex.info (`main`, `organic` and `other` shelves). Built by scripts/build_gases_csv.py
with the shared listed-pages builder; identity from PubChem where there is a formula (air has none).

A gas's index depends on temperature AND pressure. Temperature is on every row (temperature_c); the schema has no pressure
column, so the pressure is part of the variant label: "gas, 101.325 kPa", "gas, 100 kPa" (Borzsonyi 2008: 1000 mbar), "gas"
when the page states none. Condensed phases are "liquid" / "solid". Variants and temperatures are never compared or combined.
Every page is listed explicitly; variant(), suffix() only derive the label from the page name. The primary dataset is always a gas
at stated conditions: a page with unstated pressure ("gas") or a condensed phase is never primary.
"""
import re

STD = "gas, 101.325 kPa"


def variant(book, page):
    if "-liquid-" in page:
        return "liquid"
    if "-solid-" in page:
        return "solid"
    if page == "Borzsonyi":
        return "air, 100 kPa" if book == "air" else "gas, 100 kPa"
    if book == "air":
        return "dry air (370 ppm CO2), 101.325 kPa" if page.startswith("Mathar") else "dry air (450 ppm CO2), 101.325 kPa"
    if page in ("Koch", "Weber"):  # no pressure stated
        return "gas"
    return STD


def suffix(page):
    """Keeps one paper's pages apart: temperature (Peck-0C, Sinnock-liquid-90K) or wavelength band (Mathar-1.3)."""
    m = re.search(r"-(\d+(?:\.\d+)?K)$", page) or re.search(r"-(\d+C)$", page)
    if m:
        return m.group(1)
    m = re.match(r"Mathar-(\d+(?:\.\d+)?)$", page)
    return f"{m.group(1)}um" if m else None


def _gas(key, name, shelf, book, pages, formula, pubchem_name=None, temperature_c=None, note=None):
    entries = []
    for pg in pages:
        e = dict(shelf=shelf, book=book, page=pg, variant=variant(book, pg), tag_suffix=suffix(pg))
        if pg in (temperature_c or {}):
            e["temperature_c"] = temperature_c[pg]
        entries.append(e)
    return dict(key=key, name=name, pages=entries, formula=formula, pubchem_name=pubchem_name or name, note=note, density_page=None,
                materialclass="gas" if formula else "gas mixture",
                not_primary=("gas", "liquid", "solid"))  # the primary is a gas at stated conditions (unstated pressure or a condensed phase never)


_KOCH_LAMBDA_AIR = {"Koch": None}  # "Wavelength is lambda_air at 15 degC": the wavelength scale's reference, not the gas temperature
_SINNOCK_AR = [f"Sinnock-liquid-{t}K" for t in ("90", "88", "86", "83.81")] + [f"Sinnock-solid-{t}K" for t in ("83.81", "80", "70", "60", "50", "40", "30", "20")]
_SINNOCK_KR = [f"Sinnock-liquid-{t}K" for t in ("126", "122", "118", "115.95")] + [f"Sinnock-solid-{t}K" for t in ("115.95", "105", "95", "85", "75", "67")]
_SINNOCK_XE = [f"Sinnock-liquid-{t}K" for t in ("178", "174", "170", "166", "161.35")] + [f"Sinnock-solid-{t}K" for t in ("161.35", "150", "140", "130", "120", "110", "100", "90", "80")]

MATERIALS = [
    _gas("Air", "Air", "other", "air", ["Ciddor", "Birch", "Peck", "Borzsonyi", "Mathar-1.3", "Mathar-2.8", "Mathar-4.35", "Mathar-7.5"],
         None, note="dry standard air; CO2 content and pressure in the variant label"),
    _gas("N2", "Nitrogen", "main", "N2", ["Peck-15C", "Peck-0C", "Borzsonyi", "Griesmann"], "N2"),
    _gas("O2", "Oxygen", "main", "O2", ["Zhang", "Smith"], "O2"),
    _gas("Ar", "Argon", "main", "Ar", ["Peck-15C", "Peck-0C", "Bideau-Mehu", "Borzsonyi", "Larsen", "Cuthbertson"] + _SINNOCK_AR
         + ["Grace-liquid-90K", "Grace-liquid-83.81K", "Grace-solid-83.81K", "Grace-solid-20K"], "Ar",
         note="liquid (83.81-90 K) and solid (20-83.81 K) argon are labelled by phase"),
    _gas("He", "Helium", "main", "He", ["Ermolov", "Mansfield", "Borzsonyi", "Smith", "Cuthbertson"], "He"),
    _gas("Ne", "Neon", "main", "Ne", ["Bideau-Mehu", "Borzsonyi", "Cuthbertson"], "Ne"),
    _gas("Kr", "Krypton", "main", "Kr", ["Bideau-Mehu", "Borzsonyi", "Smith", "Koch", "Cuthbertson"] + _SINNOCK_KR, "Kr",
         temperature_c=_KOCH_LAMBDA_AIR, note="liquid and solid krypton are labelled by phase"),
    _gas("Xe", "Xenon", "main", "Xe", ["Bideau-Mehu", "Borzsonyi", "Koch", "Cuthbertson"] + _SINNOCK_XE
         + ["Grace-liquid-178K", "Grace-liquid-161.35K", "Grace-solid-161.35K", "Grace-solid-80K"], "Xe",
         temperature_c=_KOCH_LAMBDA_AIR, note="liquid and solid xenon are labelled by phase"),
    _gas("H2", "Hydrogen", "main", "H2", ["Peck", "Smith", "Koch"], "H2"),
    _gas("D2", "Deuterium", "main", "D2", ["Weber"], "D2", note="pressure not stated by the source"),
    _gas("CO", "Carbon monoxide", "main", "CO", ["Smith"], "CO"),
    _gas("CO2", "Carbon dioxide", "main", "CO2", ["Bideau-Mehu", "Old"], "CO2"),
    _gas("NH3", "Ammonia", "main", "NH3", ["Cuthbertson"], "NH3", note="0 degC, 760 mmHg (the page text; no CONDITIONS block)"),
    _gas("SF6", "Sulfur hexafluoride", "main", "SF6", ["Vukovic"], "SF6", note="dispersion formula based on measurements at two wavelengths"),
    _gas("CH4", "Methane", "organic", "methane", ["Loria", "Rollefson"], "CH4"),
    _gas("C2H6", "Ethane", "organic", "ethane", ["Loria"], "C2H6"),
    _gas("C2H4", "Ethylene", "organic", "ethylene", ["Loria"], "C2H4"),
    _gas("C2H2", "Acetylene", "organic", "acetylene", ["Loria"], "C2H2"),
]

_MARTONCHIK = ("Martonchik & Orton 1994: the two 'Liquid' pages carry the solid page's comment ('Phase I solid methane', and call "
               "111 K a melting point), and every page warns 'don't rely on interpolated values: most data points represent values at "
               "local maxima or minima'; interpolation is what n(633 nm) and the cross-source comparison do")
EXCLUDED_PAGES = {("organic", "methane", p): _MARTONCHIK for p in ("Martonchik-liquid-111K", "Martonchik-liquid-90K",
                                                                   "Martonchik-solid-90K", "Martonchik-solid-30K")}
OUT_OF_FAMILY = {}
