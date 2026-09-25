# Data license and attribution

**Scope.** `LICENSE` (MIT) covers the source code. This file covers the data: everything under `data/`
and every release package built by `scripts/build_release.py`.

## License of the compiled dataset

The compiled dataset is licensed under the
[Creative Commons Attribution 4.0 International license (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).
You may share and adapt it for any purpose, including commercially, provided you give attribution:
cite this dataset **and** the upstream sources below.

CC BY 4.0 is the most permissive license available here. Part of the data comes from the Materials Project,
which is itself CC BY 4.0, so the attribution requirement has to be passed on.

## Upstream sources and their terms

| Source | Used for | Terms | Cite |
|---|---|---|---|
| refractiveindex.info database | optical constants (n, k) | CC0 1.0 (public domain) | M. N. Polyanskiy, *Sci. Data* **11**, 94 (2024), [doi:10.1038/s41597-023-02898-2](https://doi.org/10.1038/s41597-023-02898-2), plus the original paper of each dataset (listed in the `sources` table) |
| Materials Project | calculated (DFT) densities, crystal-structure descriptors | CC BY 4.0 | A. Jain et al., *APL Mater.* **1**, 011002 (2013), [doi:10.1063/1.4812323](https://doi.org/10.1063/1.4812323); the MP database version is recorded in each release's `MANIFEST.json` |
| PubChem | identifiers (CID, SMILES, InChIKey, CAS), molecular weight | NCBI public data | S. Kim et al., *Nucleic Acids Res.* **51**, D1373–D1380 (2023), [doi:10.1093/nar/gkac956](https://doi.org/10.1093/nar/gkac956) |
| periodictable | x-ray and neutron scattering length densities (calculated) | public domain | P. A. Kienzle, periodictable, <https://github.com/python-periodictable/periodictable> |
| pymatgen | compositional descriptors (element data) | MIT | S. P. Ong et al., *Comput. Mater. Sci.* **68**, 314–319 (2013), [doi:10.1016/j.commatsci.2012.10.028](https://doi.org/10.1016/j.commatsci.2012.10.028) |
| RDKit | molecular descriptors, Morgan fingerprints | BSD-3-Clause | RDKit: Open-source cheminformatics, <https://www.rdkit.org> |

Literature densities cite their own papers in the `sources` table.

## Calculated vs measured

The data labels calculated values as calculated, and they are **not** measurements. This covers DFT densities
(`density_MP_DFT`, `bulk_elemental_approximation`), scattering length densities and every descriptor. The labels
are in `dataset_label`, the `sources` table and the release README. The data is provided as is, without warranty.
