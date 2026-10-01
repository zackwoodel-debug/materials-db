# Invariants

Generated from `src/materials_db/core/invariants.py` by `scripts/write_invariants_md.py`; do not edit by hand.

**FAIL** invariants block a release (`scripts/build_release.py` validation); **WARN** invariants are reported (release `MANIFEST.json` `invariants`, and `materials_db.core.audit` for the legacy database).

## A. Provenance

- **optical_rows_have_a_source** (FAIL, release): Every n,k value must be traceable to the paper or page it came from.
- **physical_rows_have_a_source** (FAIL, release): Every density, SLD and dielectric value must be traceable to its origin.
- **optical_sources_exist** (FAIL, release): A cited source must exist; a dangling id is provenance that cannot be followed.
- **physical_sources_exist** (FAIL, release): As above, for physical properties.
- **density_has_a_known_state** (FAIL, release): Every density is verified or a bulk approximation (process_condition DENSITY_STATE); an unclassified density would hide whether it describes the measured sample.
- **sources_have_a_locator** (WARN, release): A source should carry a DOI or URL so a reader can find it; reports, datasheets and handbooks often have neither.

## B. Physical sanity

- **n_is_positive_and_finite** (FAIL, release): A refractive index must be a finite positive number.
- **negative_k_only_where_reviewed** (FAIL, release): k < 0 is unphysical for a passive medium; it is allowed only as reviewed measurement noise, per dataset, down to a recorded floor (build_release.NEGATIVE_K_ALLOWED).
- **wavelength_is_positive_and_finite** (FAIL, release): Wavelengths are stored in nm and must be finite and positive.

## D. Identity

- **material_ids_are_unique** (FAIL, release): A material id names one material.
- **material_names_are_unique_after_normalization** (FAIL, release): Two materials whose names differ only in case, spacing or Unicode form would make a name lookup ambiguous.

## L. Legacy database (data/materials.db)

- **legacy_rows_have_a_reference** (WARN, legacy): The legacy data/materials.db SLD and dielectric tables should cite a reference; rows without one are kept, flagged, and never silently attributed (docs/adr/0002).
