#!/usr/bin/env python3
"""
scripts/bio_media_material_list.py
==================================
The biological-media family: buffer solutions, a cell-culture medium, human blood fractions and ex-vivo human tissues from
refractiveindex.info's `other` shelf ("Buffer solutions", "Human body"). Mixtures: formula NULL, no SLD, no structure, no density.
Each page is its own dataset labelled by the sample variant it describes (never compared with another variant). Built by
scripts/build_bio_media_csv.py with the shared listed-pages builder. Tissue optical constants vary from sample to sample: each
dataset is the one sample its source measured.
"""
SHELF = "other"


def _p(book, page, variant):
    return dict(shelf=SHELF, book=book, page=page, variant=variant)


def _b(key, name, pages, materialclass, note=None):
    return dict(key=key, name=name, pages=pages, materialclass=materialclass, note=note, density_page=None)


MATERIALS = [
    _b("PBS", "Phosphate-buffered saline (PBS)",
       [_p("PBS", "Barroso", "DPBS"), _p("PBS", "Barroso-EDTA-BSA", "DPBS + 2 mM EDTA + 0.5% BSA"), _p("PBS", "Janeiro", "10x PBS")],
       "buffer solution", note="Janeiro 10x PBS: 1.37 M NaCl, 27 mM KCl, 101.4 mM Na2HPO4, 17.6 mM KH2PO4"),
    _b("DMEM", "Dulbecco's modified Eagle's medium (DMEM)",
       [_p("BME", "Barroso", "DMEM"), _p("BME", "Barroso-FBS", "DMEM + 10% FBS"), _p("BME", "Barroso-HEPES-FBS", "HEPES-buffered DMEM + FBS")],
       "cell-culture medium"),
    _b("blood", "Human blood",
       [_p("blood", "Liu", "whole blood"), _p("blood", "Rowe", "whole blood"), _p("blood", "Liu-serum", "serum"),
        _p("blood", "Liu-plasma", "plasma")],
       "biological fluid", note=("CAUTION Liu 2019 whole blood: refractiveindex.info omits the second Sellmeier term of the published "
                                 "equation as an apparent error (the single-term equation reproduces the paper's Fig. 3(a)); the result, "
                                 "n(633 nm) = 1.348, is close to Liu's serum and plasma (1.346) and below typical whole-blood values "
                                 "(~1.38-1.40): loaded as the source gives it, not relabelled")),
    _b("adipose", "Human adipose tissue", [_p("adipose_tissue", "Yanina", None)], "biological tissue",
       note="ex-vivo abdominal adipose tissue, 23 degC"),
    _b("liver", "Human liver tissue", [_p("liver", "Giannios", None)], "biological tissue", note="ex-vivo tissue, 24 degC"),
    _b("colon", "Human colon tissue",
       [_p("colon", "Giannios-mucosa", "mucosa"), _p("colon", "Giannios-submucosa", "submucosa"), _p("colon", "Giannios-serosa", "serosa")],
       "biological tissue", note="ex-vivo tissue layers, 24 degC"),
]

EXCLUDED_PAGES = {}
_COMPOSITION = ("a two-liquid mixture series by weight fraction: how to represent composition (one material per fraction, as PDMS "
                "per cure ratio, or variants of one material) is the convention pending with Aiden. The 0 and 100 wt% end points "
                "are loaded as water, heavy water and glycerol")
OUT_OF_FAMILY = {
    "water:glycerol 20 / 50 wt% (Gupta 2022)": _COMPOSITION,
    "heavy water:glycerol 25 / 50 / 75 wt% (Sarkar 2022)": _COMPOSITION + ("; source error: the 50 and 75 wt% pages' comments "
                                                                           "say '25 wt% glycerol'"),
    "Cu:TCNQ, Li:TCNQ (Querry 1985)": "organic charge-transfer complexes, not biological media: a later batch",
}
