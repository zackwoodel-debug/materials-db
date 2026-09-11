#!/usr/bin/env python3
"""
scripts/build_checkpoint1_report.py
====================================
Step 1 checkpoint report (v2). For each of the 50 materials, lists every
RI.info page as its own dataset row labeled with its optical axis
(ordinary/extraordinary for uniaxial, alpha/beta/gamma for biaxial, or
"none" for isotropic/cubic/amorphous material), grouped by underlying
paper. Proposes a default paper per material. Adds explicit phase /
space-group notes for the three polymorph-critical materials called out
by the user: SiO2 (amorphous vs quartz), TiO2 (rutile/anatase/amorphous),
and SiO (no legitimate MP match).
"""

import json
import re
import unicodedata
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
IN_PATH = _ROOT / "data" / "ri_info_match_report.json"
OUT_PATH = _ROOT / "data" / "CHECKPOINT_1_match_table.md"
SELECTIONS_OUT = _ROOT / "data" / "step1_selections.json"
DATA_ROOT = _ROOT / "refractiveindex_db" / "database" / "data"

AMORPHOUS_KEYWORDS = ("amorphous", "fused", "glass", "glassy")

RAY_SUFFIX_RE = re.compile(r"-(o|e|alpha|beta|gamma|α|β|γ|x)(-.*)?$")

_AXIS_TOKEN_RE = re.compile(r"\bn(,k)?\([^)]*\)")
_RANGE_CLAUSE_RE = re.compile(
    r";[^;]*?[0-9][0-9.eE<>~–-]*\s*[–-]\s*[0-9][0-9.eE<>~–-]*\s*(nm|[uµ]m)[^;]*"
)


def normalize_group_name(page_name: str) -> str:
    """Identify the underlying paper/sample a page belongs to, independent of
    which optical axis (o/e/alpha/beta/gamma) it reports. Two pages only
    group together if their name is identical once the axis token and its
    wavelength-range clause are stripped -- this avoids merging distinct
    papers/samples that happen to share a filename stem (e.g. RI.info's
    'Malitson.yml' 1962 solo paper vs 'Malitson-o/e.yml' 1972 pair; or
    'Querry.yml' thin-film sample vs 'Querry-o/e.yml' bulk sapphire)."""
    s = _AXIS_TOKEN_RE.sub("", page_name)
    s = _RANGE_CLAUSE_RE.sub("", s)
    return s.strip().rstrip(";").strip()

# forced default overrides: (formula -> paper group key to prefer)
FORCED_DEFAULT = {
    "SiO2": "Malitson",     # amorphous fused silica, per user instruction
}

# materials to exclude specific non-matching candidate pages from (book
# matched by formula but the page is actually a different stoichiometry)
EXCLUDE_PAGES = {
    "SiO": {"Herguedas-SiO0.31", "Herguedas-SiO0.61", "Herguedas-SiO1.10",
            "Herguedas-SiO1.71", "Herguedas-SiO1.89", "Herguedas-SiO1.92"},
}

WANTED_POLYMORPH_KEYWORDS = {
    "CaCO3": ["calcite"],
}

# the task's original TARGETS polymorph field is sometimes a placeholder
# covering multiple possibilities (e.g. TiO2: "rutile/anatase") -- override
# with the specific polymorph of the dataset actually selected as default,
# so dataset_label reflects reality rather than the ambiguous placeholder.
DATASET_LABEL_POLYMORPH_OVERRIDE = {
    "TiO2": "rutile",
    "SiO2": "amorphous",
    "BiB3O6": "alpha-BiBO",
    "CaGdAlO4": "K2NiF4-type",
    "CaYAlO4": "K2NiF4-type",
    "Nb2O5": "amorphous",
}


def group_key(page_id: str) -> str:
    return RAY_SUFFIX_RE.sub("", page_id)


def parse_range(wl_range: str):
    m = re.match(r"([\d.]+)-([\d.]+)", wl_range)
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))


def covers_633(wl_range: str) -> bool:
    r = parse_range(wl_range)
    return bool(r) and r[0] <= 0.633 <= r[1]


AXIS_SUFFIX = {
    "ordinary (o)": "o-ray",
    "extraordinary (e)": "e-ray",
    "biaxial alpha (nα)": "alpha-axis",
    "biaxial beta (nβ)": "beta-axis",
    "biaxial gamma (nγ)": "gamma-axis",
}


def source_label(page_name: str) -> str:
    """Short 'AuthorYear' identifier from a page name, e.g.
    'Malitson and Dodge 1972: alpha-Al2O3 (Sapphire); n(o) ...' -> 'Malitson1972'."""
    head = page_name.split(":")[0]
    m = re.match(r"^([A-Za-zÀ-ɏ]+)", head)
    author = m.group(1) if m else "Unknown"
    author = unicodedata.normalize("NFKD", author).encode("ascii", "ignore").decode()
    y = re.search(r"(\d{4})", head)
    year = y.group(1) if y else ""
    return f"{author}{year}"


def make_dataset_label(polymorph: str, page_name: str, axis: str) -> str:
    """dataset_label convention agreed with the user: 'polymorph | source | axis',
    axis segment omitted when not applicable (isotropic data), polymorph segment
    omitted when the material has no specifically-named polymorph."""
    parts = []
    if polymorph:
        parts.append(polymorph)
    parts.append(source_label(page_name))
    axis_suffix = AXIS_SUFFIX.get(axis)
    if axis_suffix:
        parts.append(axis_suffix)
    return " | ".join(parts)


def get_axis(page_id: str, data_path: str) -> str:
    if not data_path:
        return "?"
    p = DATA_ROOT / data_path
    if not p.exists():
        return "?"
    try:
        raw = yaml.safe_load(open(p))
    except Exception:
        return "?"
    comments = raw.get("COMMENTS") or ""
    low = comments.lower()
    if "extraordinary" in low:
        return "extraordinary (e)"
    if "ordinary" in low:
        return "ordinary (o)"
    for greek, label in [("α", "biaxial alpha (nα)"), ("β", "biaxial beta (nβ)"), ("γ", "biaxial gamma (nγ)")]:
        if f"axis {greek}" in low or f"principal axis {greek}" in comments:
            return label
    if page_id.endswith("-o"):
        return "ordinary (o)"
    if page_id.endswith("-e"):
        return "extraordinary (e)"
    low_id = page_id.lower()
    if low_id.endswith("alpha") or low_id.endswith("α"):
        return "biaxial alpha (nα)"
    if low_id.endswith("beta") or low_id.endswith("β"):
        return "biaxial beta (nβ)"
    if low_id.endswith("gamma") or low_id.endswith("γ"):
        return "biaxial gamma (nγ)"
    return "none (isotropic/cubic/amorphous)"


def score(dataset_pages: list, formula: str) -> tuple:
    names = " ".join(p["page_name"].lower() for p in dataset_pages)
    ranges_ok_633 = any(covers_633(p["wl_range"]) for p in dataset_pages)
    is_thin_film = "thin film" in names or "nanoparticle" in names or "nanocrystalline" in names
    wanted_kw = WANTED_POLYMORPH_KEYWORDS.get(formula, [])
    matches_wanted = any(kw in names for kw in wanted_kw) if wanted_kw else True
    n_pages = len(dataset_pages)
    return (matches_wanted, ranges_ok_633, not is_thin_film, n_pages)


def is_amorphous(pages: list) -> bool:
    text = " ".join((p["page"] + " " + p["page_name"] + " " + comment_for(p)).lower() for p in pages)
    return any(kw in text for kw in AMORPHOUS_KEYWORDS)


def comment_for(p: dict) -> str:
    if not p.get("data_path"):
        return ""
    path = DATA_ROOT / p["data_path"]
    if not path.exists():
        return ""
    try:
        raw = yaml.safe_load(open(path))
    except Exception:
        return ""
    return raw.get("COMMENTS") or ""


def main():
    report = json.load(open(IN_PATH))
    selections = {}
    lines = []
    lines.append("# CHECKPOINT 1 (v2): RI.info Match Table (50 oxides)\n")
    lines.append("All 50/50 materials have >=1 match in refractiveindex.info. Every optical axis "
                  "(ordinary/extraordinary, or biaxial alpha/beta/gamma) is now listed as its own row -- "
                  "for a birefringent material BOTH axes are needed, not a choice between them. "
                  "**Bold** dataset name = proposed default paper for that material.\n")

    needs_decision = []

    for r in report:
        formula = r["formula"]
        excl = EXCLUDE_PAGES.get(formula, set())
        datasets = [d for d in r["datasets"] if d["page"] not in excl]

        lines.append(f"\n## {r['idx']}. {r['name']} ({formula})" + (f" -- list polymorph: {r['polymorph']}" if r['polymorph'] else ""))

        if not datasets:
            lines.append("- **NO USABLE RI.info MATCH** (all candidate pages excluded -- see notes).\n")
            continue

        groups = {}
        for d in datasets:
            gk = normalize_group_name(d["page_name"])
            groups.setdefault(gk, []).append(d)

        scored = [(score(pages, formula), gk, pages) for gk, pages in groups.items()]
        scored.sort(key=lambda x: x[0], reverse=True)

        forced = FORCED_DEFAULT.get(formula)
        if forced:
            scored.sort(key=lambda x: 0 if any(p["page"].startswith(forced) for p in x[2]) else 1)

        if len(scored) > 1:
            needs_decision.append(r["idx"])

        effective_polymorph = DATASET_LABEL_POLYMORPH_OVERRIDE.get(formula, r["polymorph"])

        for i, (s, gk, pages) in enumerate(scored):
            is_default = (i == 0)
            p0 = pages[0]
            label = p0["page"] if len(pages) == 1 else group_key(p0["page"])
            marker = "**" if is_default else ""
            lines.append(f"- {marker}{p0['shelf']}/{p0['book']}/{label} -- {gk}{marker}"
                         + (" (DEFAULT)" if is_default else ""))
            for p in pages:
                axis = get_axis(p["page"], p["data_path"])
                c633 = "yes" if covers_633(p["wl_range"]) else "no"
                dlabel = make_dataset_label(effective_polymorph, p["page_name"], axis) if is_default else None
                dlabel_str = f", dataset_label=`{dlabel}`" if dlabel else ""
                lines.append(f"    - `{p['page']}` axis={axis}, range={p['wl_range']}, covers 633nm: {c633}{dlabel_str} -- {p['page_name']}")

        if excl:
            lines.append(f"- Excluded as non-matching stoichiometry: {', '.join(sorted(excl))}")

        lines.append("")

        default_gk, default_pages = scored[0][1], scored[0][2]
        selections[formula] = dict(
            idx=r["idx"],
            name=r["name"],
            polymorph=r["polymorph"],
            effective_polymorph=effective_polymorph,
            amorphous_default=is_amorphous(default_pages),
            default_paper=default_gk,
            axes=[
                dict(page=p["page"], axis=get_axis(p["page"], p["data_path"]),
                     data_path=p["data_path"], wl_range=p["wl_range"],
                     dataset_label=make_dataset_label(effective_polymorph, p["page_name"], get_axis(p["page"], p["data_path"])))
                for p in default_pages
            ],
        )

    lines.insert(3, f"\n**{len(needs_decision)} materials have multiple candidate papers needing a decision "
                     f"(axis splits of the same paper don't count):** {', '.join(str(i) for i in needs_decision)}\n")

    OUT_PATH.write_text("\n".join(lines))
    print(f"Wrote {OUT_PATH}")

    SELECTIONS_OUT.write_text(json.dumps(selections, indent=2))
    print(f"Wrote {SELECTIONS_OUT}")
    amorphous_defaults = [f for f, s in selections.items() if s["amorphous_default"]]
    print(f"Auto-detected amorphous/glass defaults ({len(amorphous_defaults)}): {amorphous_defaults}")


if __name__ == "__main__":
    main()
