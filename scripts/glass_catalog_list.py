#!/usr/bin/env python3
"""
scripts/glass_catalog_list.py
=============================
Manufacturer optical-glass catalogs from refractiveindex.info's `specs` shelf (SCHOTT, OHARA, HIKARI, CDGM, HOYA, SUMITA, LZOS
and the SCHOTT / HIKARI 'misc' books): every glass page is one material, generated from the catalog (not typed by hand), built by
scripts/build_glass_catalogs_csv.py with the shared listed-pages builder.

  * a material = one catalog glass (name "<MAKER> <glass>", key "<BOOK>/<glass>"); formula NULL (compositions are proprietary);
  * n: the manufacturer's Sellmeier-type formula (sampled adaptively, like every formula page), k: its internal-transmittance table;
  * density: the datasheet's (PROPERTIES.density, kg/m3), cited to the catalog; datasheet extras (nd, Vd, glass code, dPgF,
    thermal expansion, catalog status) go into extra columns of the family table;
  * a page already loaded by another family (SCHOTT N-BK7, B 270, BOROFLOAT 33, ... in the glasses family) is not loaded again;
  * the `popular_glass` shelf is not loaded: its pages ARE catalog pages (the same data files); it serves as refractiveindex.info's
    own list of cross-maker equivalents (N-BK7 ~ S-BSL7 ~ J-BK7A ~ H-K9L ~ BSC7 ~ K-BK7 ~ K8) for the ML splits.
ML splits (scripts/generate_ml_splits.py): optical equivalents share a group -- the same 6-digit glass code (nd, Vd), or listed
together on a popular_glass page -- across makers; a class containing one of the glasses family's datasheet glasses joins that
glass's group (existing materials never move).
"""
import re
from functools import lru_cache
from pathlib import Path

import yaml

RI = Path(__file__).resolve().parents[1] / "refractiveindex_db" / "database"
BOOKS = ["SCHOTT-optical", "OHARA-optical", "HIKARI-optical", "CDGM-optical", "HOYA-optical", "SUMITA-optical", "LZOS-optical",
         "SCHOTT-misc", "HIKARI-misc"]


@lru_cache(maxsize=1)
def catalog():
    out = {}
    for e in yaml.safe_load(open(RI / "catalog-nk.yml")):
        for b in e.get("content", []):
            if "BOOK" in b:
                out[(e["SHELF"], b["BOOK"])] = [p for p in b.get("content", []) if isinstance(p, dict) and p.get("data")]
    return out


def page_yaml(data_path):
    return yaml.safe_load(open(RI / "data" / data_path))


def glass_code(props):
    """The 6-digit code nnnvvv: (nd - 1) to 3 decimals and Vd to 1 decimal, from the datasheet's own glass_code when it has one
    (some carry the density as a suffix, 517642.251), else from its nd and Vd."""
    c = props.get("glass_code")
    if c is not None:  # YAML reads 005210 (P-SF68, nd 2.005) as the integer 5210: restore the leading zeros
        digits = re.sub(r"\D", "", str(c).split(".")[0]).zfill(6)
        if len(digits) == 6:
            return digits
    if props.get("nd") is not None and props.get("Vd") is not None:  # nd >= 2 keeps the last three digits (2.005 -> 005)
        return f"{round((float(props['nd']) - 1) * 1000) % 1000:03d}{round(float(props['Vd']) * 10):03d}"
    return None


def code_from_nd(props):
    """The 6-digit code the page's OWN nd and Vd give. It differs from the datasheet code only for precision-moulding grades
    (SUMITA '(M)', OHARA '...P'): their nd / Vd are after moulding (the index drops on reheating), their code the base glass's."""
    if props.get("nd") is None or props.get("Vd") is None:
        return None
    return f"{round((float(props['nd']) - 1) * 1000) % 1000:03d}{round(float(props['Vd']) * 10):03d}"


def extras(props, comments):
    """Datasheet values for the family table. catalog_status only from the datasheet's own glass_status field; the page's free
    comment (e.g. 'For mold lens', 'anneal rate: 4 degC/h') is kept verbatim, whitespace-normalized, as catalog_comment."""
    cte = props.get("thermal_expansion") or []
    first = cte[0] if isinstance(cte, list) and cte else {}
    comment = " ".join(str(comments or "").split()) or None
    code, from_nd = glass_code(props), code_from_nd(props)
    return dict(nd=props.get("nd"), vd=props.get("Vd"), glass_code=code,
                glass_code_from_nd=from_nd if from_nd and code and from_nd != code else None, dpgf=props.get("dPgF"),
                cte_per_k=first.get("value"), cte_range_k=first.get("temperature_range"), catalog_status=props.get("glass_status"),
                catalog_comment=comment)


def materials(already_loaded, excluded_elsewhere=None):
    """One entry per catalog glass that no other family loads OR EXCLUDED. already_loaded: data paths of every other family;
    excluded_elsewhere: {(shelf, book, page): reason} of pages another family excluded on review (e.g. SCHOTT DURAN, one
    inconsistent point: the glasses family's decision stands). Returns (materials, {page: (gap_kind, reason)})."""
    excluded_elsewhere = excluded_elsewhere or {}
    out, skipped, seen = [], {}, set()
    for book in BOOKS:
        maker = book.split("-")[0]
        for p in catalog()[("specs", book)]:
            if p["data"] in seen:  # refractiveindex.info's catalog lists 17 pages twice (the same data file)
                continue
            seen.add(p["data"])
            if p["data"] in already_loaded:
                skipped[("specs", book, p["PAGE"])] = ("already_loaded", "already a material of another family (same data file)")
                continue
            if ("specs", book, p["PAGE"]) in excluded_elsewhere:
                skipped[("specs", book, p["PAGE"])] = ("excluded_page", "excluded by another family on review: "
                                                       + excluded_elsewhere[("specs", book, p["PAGE"])])
                continue
            d = page_yaml(p["data"])
            props = d.get("PROPERTIES") or {}
            out.append(dict(key=f"{book}/{p['PAGE']}", name=f"{maker} {p['PAGE']}", pages=[dict(shelf="specs", book=book, page=p["PAGE"])],
                            formula=None, note=None, materialclass="optical glass",
                            density_page=("specs", book, p["PAGE"]) if props.get("density") else None,
                            extra=extras(props, str(d.get("COMMENTS") or ""))))
    return out, skipped


def popular_equivalents():
    """refractiveindex.info's popular_glass pages: each book lists one glass type's equivalents across makers (by data path)."""
    return {book: [p["data"] for p in pages] for (shelf, book), pages in catalog().items() if shelf == "popular_glass"}
