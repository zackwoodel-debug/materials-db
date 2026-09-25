# Descriptor inputs

`scripts/build_release.py` reads these files to fill the `chemical_descriptors` table of the release database. Everything
here is committed, so a release builds offline and needs no API key.

| file | what it is | how it is made |
|---|---|---|
| `mp_structural.json` | crystal-structure descriptors of every Materials Project entry that a family build chose (space group, conventional-cell lattice, Z, DFT density, hull energy, band gap) | `python3 scripts/fetch_mp_structure_descriptors.py` (needs `MP_API_KEY` in `.env`); records the MP database version |
| `polymer_repeat_units.csv` | repeat-unit SMILES (`*` = attachment point) for every polymer whose source states a composition | curated: standard polymer chemistry, or derived from the IUPAC name on the refractiveindex.info page; each is checked against the source's repeat-unit formula by `tests/test_release_build.py` |
| `formula_issues.csv` | recorded formulas that are known to be wrong; formula-based descriptors are withheld for them | curated, with the evidence |

Rules, fixed in `scripts/release_descriptors.py`:

- Every material gets a row. A descriptor that does not apply, or whose input is missing, is NULL, and `descriptor_json`
  says which of the two and why. Nothing is guessed or zero-filled.
- Molecular descriptors (RDKit) are computed for polymer repeat units only. A PubChem SMILES of an inorganic solid, such as
  `[Na+].[Cl-]`, is formula-unit notation, so its TPSA, logP or H-bond counts describe nothing real. Exact mass and heavy-atom
  count are still defined for any formula unit, so inorganic materials get those two from their formula.
- Structural descriptors come from the MP entry the family build already chose for the density. They are never a new pick.
  `applies_to` says whether the entry is the material itself or only a crystalline reference, which is the case for an
  amorphous or film sample or a bulk-approximated density.

Known source problems found while curating:

- **PDCBT:** refractiveindex.info gives `(C42H56O4S2)n` but names a quaterthiophene, which has four sulfur atoms
  (`(C42H56O4S4)n`). See `formula_issues.csv`.
- **PTB7:** the page's name says "(2-ethylhexyl)carbonyl", but its formula (O4) requires the ester, which is the actual
  structure of PTB7. The repeat unit uses the ester.
