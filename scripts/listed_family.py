#!/usr/bin/env python3
"""
scripts/listed_family.py
========================
Builder shared by the families whose materials are multicomponent products with NO single formula (glasses, index-matching
liquids, adhesives, mounting media): every refractiveindex.info page is listed explicitly in the family's material list, with the
sample variant it describes. Writes data/step1_selections_<stem>.json, data/<csv>.csv (oxides_50.csv column template +
materialclass + selection_key) and data/<gaps>.csv. Offline: no Materials Project or PubChem entry exists for such a product.

  * pages are resolved through refractiveindex.info's catalog-nk.yml; each is its own dataset labelled "variant | source";
  * primary dataset: ambient temperature, measured before model fits, then the widest page covering 633 nm (as the other families);
  * density only where the manufacturer's page states it (PROPERTIES.density, kg/m3, with its temperature when stated), cited to
    that datasheet; otherwise NULL;
  * formula NULL, so no SLD and no MP entry; n_633 of formula pages evaluated exactly.
"""
import json
import re
import sys
from pathlib import Path

import pandas as pd
import yaml

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_oxides_csv as base  # noqa: E402
from build_chalcogenides_csv import exact_formula_n633  # noqa: E402
from dataset_kind import is_model_fit  # noqa: E402
from match_ri_info_chalcogenides import label_of, scan_page, strip, tag_of  # noqa: E402
from match_ri_info_liquids import page_temperature_c  # noqa: E402
from match_ri_info_semiconductors import ambient  # noqa: E402

DATA = _ROOT / "data"
RI = _ROOT / "refractiveindex_db" / "database"


def catalog_pages():
    out = {}
    for e in yaml.safe_load(open(RI / "catalog-nk.yml")):
        for b in e.get("content", []):
            for p in b.get("content", []) if "BOOK" in b else []:
                if p.get("data"):
                    out[(e["SHELF"], b["BOOK"], p["PAGE"])] = (p["data"], strip(p.get("name")))
    return out


def ref_year(path):
    """The year of a datasheet reference, from its download link (.../download/data/2017/...) or its text."""
    raw = str(yaml.safe_load(open(RI / "data" / path)).get("REFERENCES") or "")
    m = re.search(r"/data/(\d{4})/", raw) or re.search(r"\b(?:19|20)\d{2}\b", strip(raw))
    return int(m.group(1) if m.lastindex else m.group(0)) if m else None


def source_tag(shelf, book, page, title, path):
    """Glass-shelf pages cite a paper ('Rubin 1985: ...' -> Rubin1985); catalog pages cite a manufacturer datasheet
    ('.../download/data/2017/schott_...' -> SCHOTT2017)."""
    if shelf == "specs":
        year = ref_year(path)
        return book.split("-")[0].upper() + (str(year) if year else "")
    return tag_of(page, title)


def build(MATERIALS, EXCLUDED_PAGES, OUT_OF_FAMILY, csv_stem, selections_stem, gaps_stem, formula_null_reason, density_null_reason,
          source_label):
    pages = catalog_pages()
    selections, rows, gaps = {}, [], []
    for i, mat in enumerate(MATERIALS, start=1):
        axes = []
        for shelf, book, page, variant in mat["pages"]:
            if (shelf, book, page) in EXCLUDED_PAGES:
                raise SystemExit(f"{page} is both listed and excluded")
            path, title = pages[(shelf, book, page)]
            s = scan_page(path)
            tag = source_tag(shelf, book, page, title, path)
            axes.append(dict(page=page, axis=None, phase=variant, data_path=path, span_um=s["span_um"], kind=s["kind"],
                             dispersion=s["dispersion"], comments=s["comments"], temperature_c=page_temperature_c(path, title + " " + s["comments"]),
                             tag=tag, dataset_label=label_of(variant, tag, None), shelf=shelf, book=book))
        axes.sort(key=lambda a: (not ambient(a), is_model_fit(a["data_path"]), not a["span_um"][0] <= 0.633 <= a["span_um"][1],
                                 a["span_um"][0] - a["span_um"][1]))
        labels = [a["dataset_label"] for a in axes]
        assert len(labels) == len(set(labels)), labels
        selections[mat["key"]] = dict(name=mat["name"], formula=None, source=f"{source_label} (every listed page is its own dataset; "
                                      "primary: ambient, measured before model fits, widest covering 633 nm)", axes=axes)

        first, flags = axes[0], []
        interp = base.interpolate_axis(first["data_path"])
        flags += [f"[{first['page']}] {f}" for f in interp.pop("flags")]
        row = dict(idx=i, name=mat["name"], formula=None, polymorph=None, materialclass=mat["materialclass"], selection_key=mat["key"],
                   ri_shelf=first["shelf"], ri_book=first["book"], ri_page_primary=first["page"], axis_primary=None,
                   n_633=exact_formula_n633(first["data_path"], interp["n_633"]), k_633=interp["k_633"],
                   ri_wl_min_nm=interp["wl_min_nm"], ri_wl_max_nm=interp["wl_max_nm"])
        for a in axes[1:]:
            other = base.interpolate_axis(a["data_path"])
            other.pop("flags")
            n633 = exact_formula_n633(a["data_path"], other["n_633"])
            flags.append(f"additional dataset {a['dataset_label']}: n(633 nm)={n633}" + (f", k={other['k_633']}" if other["k_633"] is not None else ""))
        if mat["density_page"]:
            path = pages[mat["density_page"]][0]
            d = yaml.safe_load(open(RI / "data" / path))
            rho = (d.get("PROPERTIES") or {}).get("density")
            if not rho:
                raise SystemExit(f"{mat['key']}: density page {mat['density_page']} states no density")
            refs = strip(d.get("REFERENCES"))
            row.update(density_g_cm3=float(rho[0]["value"]) / 1000.0, density_source="literature (manufacturer datasheet)",
                       density_citation_title=" ".join(refs.split())[:300], density_citation_year=ref_year(path))
            if rho[0].get("temperature") is not None:  # stated in kelvin
                row["density_temperature_c"] = round(float(rho[0]["temperature"]) - 273.15, 2)
            flags.append(f"density {row['density_g_cm3']} g/cm3 stated by the manufacturer's datasheet ({mat['density_page'][2]})")
        else:
            flags.append(density_null_reason)
        flags.append(formula_null_reason)
        if len(axes) > 1:
            flags.append(f"{len(axes)} datasets; n_633/k_633 are the primary ({first['dataset_label']})")
        if mat["note"]:
            flags.append(mat["note"])
        row["flags"] = base.FLAG_JOIN.join(flags)
        rows.append(row)
    for (shelf, book, page), why in EXCLUDED_PAGES.items():
        gaps.append(dict(key=f"{shelf}/{book}/{page}", name=page, gap_kind="excluded_page", reason=why))
    for k, why in OUT_OF_FAMILY.items():
        gaps.append(dict(key=k, name=k, gap_kind="out_of_family", reason=why))
    template = list(pd.read_csv(DATA / "oxides_50.csv", nrows=0).columns)
    df = pd.DataFrame(rows)
    df = df.reindex(columns=template + [c for c in df.columns if c not in template])
    df.to_csv(DATA / f"{csv_stem}.csv", index=False)
    (DATA / f"step1_selections_{selections_stem}.json").write_text(json.dumps(selections, indent=1, ensure_ascii=False))
    pd.DataFrame(gaps).to_csv(DATA / f"{gaps_stem}.csv", index=False)
    print(f"Wrote {csv_stem}.csv: {len(df)} rows; {sum(len(v['axes']) for v in selections.values())} datasets; {gaps_stem}.csv: {len(gaps)} rows")
    for k, v in selections.items():
        print(f"  {k:<12} {len(v['axes']):>2} datasets; primary {v['axes'][0]['dataset_label']!r}")

