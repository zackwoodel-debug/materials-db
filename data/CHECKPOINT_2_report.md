# CHECKPOINT 2: data/oxides_50.csv

50 rows x 38 columns. 47/50 rows carry at least one flag (mostly benign: "N CAS numbers on
record, took primary"). 3 rows are fully clean (no flags): check `flags` column for detail.

## NULL counts per column

| column | NULL count | why |
|---|---|---|
| polymorph | 20 | only materials with an explicit named polymorph in the task list have one |
| pubchem_cid / smiles / inchikey / molecular_weight | 16 | 11 not found on PubChem by name, 5 formula mismatches (nulled intentionally) |
| cas_number | 18 | same 16, plus 2 found compounds with no curated CAS on file |
| pubchem_formula_match | 11 | NULL = never found by name (vs FALSE = found but wrong formula) |
| mp_id / mp_space_group / mp_energy_above_hull_ev | 5 | 4 forced (amorphous RI.info default: SiO, SiO2, GeO2, Ta2O5) + 1 not in MP at all (LuAl3(BO3)4) |
| density_g_cm3 / SLD columns | 1 | LuAl3(BO3)4 -- no PubChem, no MP, no literature value plugged in either |
| n_633 | 2 | CuO, Cu2O -- their only RI.info dataset is deep-UV only (10-35nm), doesn't reach 633nm |
| k_633 | 40 | most transparent oxides have no measured absorption in the visible (k~0, correctly left NULL rather than assumed) |
| axis_2 / axis_3 + their n_633/k_633 | 24 / 44 | count of materials with 2 or 3 optical axes (birefringent/biaxial) |

## Major findings

### 1. Four more "TiO2-style" polymorph traps found and corrected
Same issue as TiO2 (lowest energy_above_hull != the experimentally relevant phase). In each
case the correct phase is a different MP entry within ~1 meV/atom of the ground state --
essentially degenerate in DFT, but a structurally different polymorph:

| Material | MP lowest-hull (wrong) | Used instead | Why |
|---|---|---|---|
| BaB2O4 (BBO) | mp-540659, R-3c #167 (centrosymmetric alpha-phase) | **mp-5730, R3c #161** (+0.5 meV/atom) | Our RI.info data (Eimerl/Tamosauskas) is the noncentrosymmetric beta-BBO NLO crystal; R-3c has no second-harmonic activity, wrong phase entirely |
| LaAlO3 | mp-1080060, Imma #74 | **mp-2920, R-3c #167** (+0.3 meV/atom) | R-3c is the standard room-temperature rhombohedral LaAlO3 phase |
| LiIO3 | mp-23384, P4_2/n #86 (tetragonal) | **mp-22955, P6_3 #173** (+0.9 meV/atom) | Our RI.info data is uniaxial (o/e pair), which requires a hexagonal/trigonal structure -- P4_2/n is the wrong symmetry class entirely; P6_3 is the known LiIO3 structure |
| CsLiB6O10 (CLBO) | mp-1019715, I2_12_12_1 #24 | **mp-5990, I-42d #122** (+0.8 meV/atom) | I-42d is the documented tetragonal CLBO structure |

### 2. Five materials still flagged `polymorph_ambiguity` -- no strong prior, took lowest-hull, needs your call
- **#4 BeAl6O10** -- mp-560974, P2_1/c #14. No confident literature space group on hand to verify against.
- **#5 CaGdAlO4** / **#6 CaYAlO4** -- both landed on I4mm #107 (noncentrosymmetric). I expected the more common K2NiF4-type I4/mmm #139 (centrosymmetric); MP's I4mm entries are at Ehull 0.027/0.043 eV (26-43 meV/atom) above their own ground state -- not a close call like the four above, so I did NOT override. Worth checking against the Loiko et al. 2017 paper's stated space group.
- **#10 BiB3O6 (BiBO)** -- mp-554718, Pca2_1 #29 (Ehull=0). Literature (Hellwig et al.) describes room-temp BiBO as monoclinic C2 #5; MP does have a C2 entry (mp-23349) but at +18.7 meV/atom -- a much bigger gap than the four confirmed corrections above, so this doesn't look like simple DFT near-degeneracy. Flagged rather than guessed.
- **#33 Nb2O5** -- mp-581967, P2 #3 (Ehull=0). Nb2O5 has many known polymorphs (T/TT/H/B/M); none of MP's lowest few entries obviously match the commonly-cited H-Nb2O5 (monoclinic P2/m #10), and RI.info's Franta/Lemarchand/Horcholle datasets don't state which polymorph they measured. Genuinely unresolved.

### 3. PubChem formula mismatches (fields correctly NULLed, not silently accepted)
- **BiB3O6**: name search resolved to BBiO3 (different boron:bismuth ratio)
- **Bi12GeO20**: resolved to Bi4Ge3O12 -- note both compounds are informally called "BGO" in the literature (sillenite vs. eulytite structure); we want the sillenite (Bi12GeO20) per your material list
- **Pb5Ge3O11**: resolved to GeO3Pb (simpler 1:1 lead germanate)
- **KNbO3**: resolved to K8Nb6O19 (a polyoxoniobate, not the perovskite)
- **YAG (Y3Al5O12)**: resolved to AlO3Y = YAlO3 (YAP perovskite, a real but different yttrium aluminate -- easy mix-up with YAG garnet)

### 4. No PubChem match by name at all (11 -- allowed to be NULL per task)
BeAl6O10, CaGdAlO4, CaYAlO4, BaB2O4, CsLiB6O10, LuAl3(BO3)4, Fe2O3, Fe3O4, Lu3Al5O12, SrMoO4, Tb3Ga5O12.
Mostly mineral/technical names PubChem doesn't index under the name I queried; likely resolvable
with alternate names/CIDs if you want that extra pass, but left NULL for now per the task's rule.

### 5. LuAl3(BO3)4 -- fully unresolved (no PubChem, no MP, no density)
This is the only material with NULL density and therefore NULL SLD (x-ray and neutron). If you
have a literature density for this borate, I'll wire it in; otherwise it ships with SLD columns NULL.

### 6. Amorphous/glass overrides -- no MP pairing, literature density used instead
SiO (2.13 g/cm3), SiO2 (2.20 g/cm3, per your instruction), GeO2 (3.65 g/cm3, fused/vitreous),
Ta2O5 (7.90 g/cm3, amorphous thin film vs. 8.37 crystalline). All flagged "verify before use" --
these are commonly-cited literature values, not sourced from a specific paper per material.

### 7. CuO, Cu2O -- n_633/k_633 correctly NULL
Their only RI.info match (Brimhall for CuO, Querry for Cu2O) is deep-UV only (10-35 nm), nowhere
near 633nm. No visible-range optical data exists in RI.info for these two oxides.

### 8. Birefringent/biaxial materials -- extra axis columns
`axis_2`/`n_633_axis2`/`k_633_axis2` (24 materials) and `axis_3`/`n_633_axis3`/`k_633_axis3`
(6 biaxial materials) hold the extraordinary/second-and-third-principal-axis values alongside
the primary `n_633`/`k_633`/`axis_1`. This is a CSV-only extension beyond the task's original
column list -- flagging it since the DB schema (Step 3) will need a decision on how to store
multiple axes per material (see the `dataset_label`/polymorph schema gap already flagged at
CHECKPOINT 1).

## Outstanding schema question (carried over from CHECKPOINT 1)
Still unresolved: `materials` table has no `polymorph` or `dataset_label` column, needed both
for TiO2's rutile default (vs. a possible anatase second row) and for storing o/e or biaxial
axis values distinctly in Step 3. Need your call before I build the loader.
