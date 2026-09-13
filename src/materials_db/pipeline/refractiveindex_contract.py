#!/usr/bin/env python3
"""
pipeline/refractiveindex_contract.py
======================================
Pinned refractiveindex.info-database commit this pipeline's catalog-walking
and DATA-block assumptions were verified against, in the same spirit as
src/materials_db/export/modalfit_contract.py.

RI.info is a data repository, not software with an API, so there's no
"upstream drift" risk in the same sense as ModalFit -- but the catalog
structure (shelf/book/page nesting, DATA block type vocabulary) is
undocumented outside the repo's own source, and future commits could add
new DATA block types or restructure the catalog. Pin the commit any
cluster-count report or batch scoping was run against, so a re-run against
a newer clone can be diffed if counts ever look different.

Use scripts/verify_refractiveindex_pin.py <path-to-clone> to check a
clone's current commit against the pin below.
"""

RI_INFO_REPO_URL = "https://github.com/polyanskiy/refractiveindex.info-database"
RI_INFO_COMMIT_SHA = "c5c2f188e848453def5970e347399d653df2ffc2"
RI_INFO_COMMIT_DATE = "2026-09-04 06:08:29 -0400"
VERIFIED_ON = "2026-09-11"

# This is the same clone data/materials_oxide_test.db's 50-oxide pipeline
# was built against (verified via `git -C refractiveindex_db log -1`),
# used here too so batch-2 scoping is evaluated against the identical
# database state the existing pipeline already targets.

CONFIRMED_STRUCTURE = {
    "catalog_shelf_book_page_nesting": dict(
        file="database/catalog-nk.yml",
        finding=(
            "Top-level list of SHELF/DIVIDER entries. A SHELF's 'content' is a "
            "list of BOOK/DIVIDER entries. A BOOK's 'content' is a list of "
            "PAGE/DIVIDER entries. PAGE entries have a 'data' key giving the "
            "relative path to the YAML dispersion file under database/data/. "
            "Relevant shelves for inorganic (non-organic, non-glass) materials: "
            "'main' (326 book-level entries) and 'other' (miscellaneous)."
        ),
    ),
    "data_block_types": dict(
        file="database/data/**/*.yml (DATA key)",
        finding=(
            "Each dispersion YAML's DATA list holds blocks with a 'type' field. "
            "Only two families observed across the whole main+other walk: "
            "'tabulated n' / 'tabulated k' / 'tabulated nk' (discrete measured "
            "points, loaded via np.loadtxt-style parsing) and 'formula 1'-'formula 7' "
            "(analytic dispersion equations with a 'coefficients' string and a "
            "'wavelength_range'). No other type strings found in this commit."
        ),
    ),
    "book_id_as_formula": dict(
        file="database/catalog-nk.yml (BOOK key)",
        finding=(
            "A BOOK's id is usually (not always) a parseable chemical formula "
            "matching periodictable.formula() syntax (e.g. 'Al2O3', 'CaF2'). "
            "Exceptions exist: mineral/trade names with no formula-like id, "
            "compound ids with embedded stoichiometry variables (e.g. a "
            "sub-stoichiometric family sharing one BOOK id across PAGEs with "
            "different x), and multi-element alloy ids periodictable parses "
            "as literal element sequences rather than a real compound (this "
            "is usually harmless since we only need periodictable to sum "
            "atomic properties, not validate real chemistry)."
        ),
    ),
}
