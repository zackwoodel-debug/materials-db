# Property Statistics Report
_Generated 2026-06-10 09:17_

Descriptive statistics for all numerical properties in `materials_normalized.db`.
IQR = inter-quartile range (Q3−Q1). MAD = median absolute deviation.

## `chemical_descriptors` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| aromatic_rings | count | 0 | 0.0% | — | — | — | — | — | — | — |
| exact_mass | g/mol | 0 | 0.0% | — | — | — | — | — | — | — |
| hbond_acceptors | count | 0 | 0.0% | — | — | — | — | — | — | — |
| hbond_donors | count | 0 | 0.0% | — | — | — | — | — | — | — |
| heavy_atom_count | count | 0 | 0.0% | — | — | — | — | — | — | — |
| logp | dimensionless | 0 | 0.0% | — | — | — | — | — | — | — |
| rotatable_bonds | count | 0 | 0.0% | — | — | — | — | — | — | — |
| tpsa | Å² | 0 | 0.0% | — | — | — | — | — | — | — |

## `consensus_properties` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| confidence_score | dimensionless | 122 | 0.0% | 0 | 1 | 0.669 | 0.5 | 0.252 | 0.5 | 0 |
| consensus_value | mixed | 122 | 0.0% | -24 | 86 | 3.242 | 1.02 | 12.04 | 2.237 | 1.02 |
| num_sources | count | 122 | 0.0% | 1 | 2 | 1.377 | 1 | 0.4866 | 1 | 0 |
| std_dev | mixed | 122 | 0.0% | 0 | 1.202 | 0.02038 | 0 | 0.1231 | 0 | 0 |

## `consensus_summary` (view)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| confidence_score | dimensionless | 122 | 0.0% | 0 | 1 | 0.669 | 0.5 | 0.252 | 0.5 | 0 |
| consensus_value | mixed | 122 | 0.0% | -24 | 86 | 3.242 | 1.02 | 12.04 | 2.237 | 1.02 |
| num_sources | count | 122 | 0.0% | 1 | 2 | 1.377 | 1 | 0.4866 | 1 | 0 |
| std_dev | mixed | 122 | 0.0% | 0 | 1.202 | 0.02038 | 0 | 0.1231 | 0 | 0 |

## `legacy_calculated_sld` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| energy_ev | eV | 68 | 0.0% | 8048 | 1.748e+04 | 1.188e+04 | 1.1e+04 | 3547 | 3858 | 1976 |
| frequency_hz | Hz | 0 | 100.0% | — | — | — | — | — | — | — |
| sld_neutron_imag | Å⁻² | 0 | 100.0% | — | — | — | — | — | — | — |
| sld_neutron_real | Å⁻² | 68 | 0.0% | -5.61e-07 | 4.507e-06 | 1.627e-06 | 1.411e-06 | 1.605e-06 | 2.799e-06 | 1.348e-06 |
| sld_xray_imag | Å⁻² | 68 | 0.0% | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| sld_xray_real | Å⁻² | 68 | 0.0% | 7.556e-06 | 0.0001315 | 2.878e-05 | 1.089e-05 | 3.287e-05 | 2.457e-05 | 2.012e-06 |
| wavelength_nm | nm | 68 | 0.0% | 0.07093 | 0.1541 | 0.1131 | 0.1137 | 0.03052 | 0.03628 | 0.02537 |

## `legacy_calculated_slds` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| energy_ev | eV | 46 | 0.0% | 8040 | 1.74e+04 | 1.272e+04 | 1.272e+04 | 4732 | 9360 | 4680 |
| neutron_sld_imag | Å⁻² | 0 | 100.0% | — | — | — | — | — | — | — |
| neutron_sld_real | Å⁻² | 46 | 0.0% | -5.61e-07 | 5.728e-06 | 2.052e-06 | 1.813e-06 | 1.863e-06 | 3.129e-06 | 1.585e-06 |
| wavelength_nm | nm | 46 | 0.0% | 0.07093 | 0.1541 | 0.1125 | 0.1125 | 0.04202 | 0.08313 | 0.04156 |
| xray_sld_imag | Å⁻² | 0 | 100.0% | — | — | — | — | — | — | — |
| xray_sld_real | Å⁻² | 46 | 0.0% | 7.556e-06 | 0.0001315 | 2.691e-05 | 1.174e-05 | 2.93e-05 | 2.41e-05 | 2.862e-06 |

## `legacy_chemical_descriptors` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| value[BertzCT] | dimensionless | 8 | 0.0% | 0 | 731.9 | 138.4 | 40.87 | 249.1 | 102.1 | 39.06 |
| value[ExactMolWt] | g/mol | 16 | 0.0% | 18.01 | 733.6 | 142 | 90.7 | 174.3 | 72.31 | 37.7 |
| value[FractionCSP3] | dimensionless | 20 | 0.0% | 0 | 1 | 0.3917 | 0 | 0.4719 | 0.9625 | 0 |
| value[MolLogP] | dimensionless | 18 | 0.0% | -1.507 | 10.61 | 1.108 | -0.00195 | 2.82 | 1.774 | 0.82 |
| value[MolWt] | g/mol | 22 | 0.0% | 18.02 | 734.1 | 137.8 | 101 | 151.6 | 89.65 | 44.95 |
| value[NumAromaticRings] | count | 20 | 0.0% | 0 | 3 | 0.2 | 0 | 0.6959 | 0 | 0 |
| value[NumHAcceptors] | count | 20 | 0.0% | 0 | 8 | 1.45 | 1 | 1.877 | 2 | 1 |
| value[NumHDonors] | count | 20 | 0.0% | 0 | 3 | 0.5 | 0 | 0.8885 | 1 | 0 |
| value[NumHeavyAtoms] | count | 10 | 0.0% | 1 | 22 | 7.1 | 4.5 | 6.919 | 5.5 | 3 |
| value[NumRings] | count | 10 | 0.0% | 0 | 1 | 0.1 | 0 | 0.3162 | 0 | 0 |
| value[NumRotatableBonds] | count | 20 | 0.0% | 0 | 38 | 2.6 | 0 | 8.45 | 1 | 0 |
| value[TPSA] | Å² | 18 | 0.0% | 0 | 111.2 | 27.13 | 23.27 | 29.03 | 35.18 | 20.23 |
| value[exact_mass] | g/mol | 10 | 0.0% | 18.01 | 733.6 | 143.1 | 70.03 | 213.6 | 55.55 | 34.05 |
| value[h_bond_acceptors] | count | 10 | 0.0% | 0 | 8 | 1.6 | 1 | 2.413 | 2 | 1 |
| value[h_bond_donors] | count | 10 | 0.0% | 0 | 2 | 0.3 | 0 | 0.6749 | 0 | 0 |
| value[logP] | dimensionless | 10 | 0.0% | -1.029 | 10.61 | 1.081 | -0.0039 | 3.479 | 1.17 | 0.7169 |
| value[rotatable_bonds] | count | 10 | 0.0% | 0 | 38 | 4.1 | 0 | 11.92 | 1 | 0 |

## `legacy_dielectric` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| dielectric_imag | dimensionless | 6 | 71.43% | 0.01 | 20.7 | 3.808 | 0.3 | 8.294 | 1.145 | 0.275 |
| dielectric_real | dimensionless | 21 | 0.0% | -24 | 86 | 12.73 | 3.9 | 26.92 | 9.1 | 5.9 |
| energy_ev | eV | 0 | 100.0% | — | — | — | — | — | — | — |
| frequency_hz | Hz | 21 | 0.0% | 0 | 3e+14 | 4.286e+13 | 1000 | 1.076e+14 | 1000 | 1000 |
| temperature_C | °C | 21 | 0.0% | 25 | 25 | 25 | 25 | 0 | 0 | 0 |
| wavelength_nm | nm | 3 | 85.71% | 633 | 633 | 633 | 633 | 0 | 0 | 0 |

## `legacy_dielectrics` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| frequency_hz | Hz | 9 | 0.0% | 1000 | 1000 | 1000 | 1000 | 0 | 0 | 0 |
| imag_permittivity | dimensionless | 3 | 66.67% | 0 | 0.05 | 0.02 | 0.01 | 0.02646 | 0.025 | 0.01 |
| real_permittivity | dimensionless | 9 | 0.0% | 2.1 | 80.1 | 13.72 | 3.5 | 25.12 | 6.8 | 1.4 |
| temperature_C | °C | 9 | 0.0% | 20 | 25 | 23.89 | 25 | 2.205 | 0 | 0 |

## `legacy_materials` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| density_g_cm3 | g/cm³ | 23 | 0.0% | 0.789 | 19.32 | 3.436 | 1.32 | 4.321 | 3.035 | 0.35 |
| molecular_weight | g/mol | 23 | 0.0% | 18.02 | 6.643e+04 | 3118 | 81.38 | 1.381e+04 | 96.38 | 29.38 |

## `legacy_optical_nk` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| k | dimensionless | 650 | 76.94% | 0 | 13.78 | 0.4056 | 5.202e-05 | 1.321 | 0.0004822 | 5.193e-05 |
| n | dimensionless | 2819 | 0.0% | 0.13 | 6.709 | 1.501 | 1.474 | 0.371 | 0.09131 | 0.04676 |
| temperature_C | °C | 1569 | 44.34% | 19.85 | 25 | 20.15 | 19.85 | 1.017 | 0.25 | 0 |
| wavelength_nm | nm | 2819 | 0.0% | 191 | 3000 | 1125 | 964.5 | 648.8 | 838.4 | 392.1 |

## `legacy_pubchem_data` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| HBondAcceptors | count | 8 | 52.94% | 0 | 8 | 2 | 1.5 | 2.563 | 1.25 | 0.5 |
| HBondDonors | count | 8 | 52.94% | 0 | 2 | 0.5 | 0 | 0.7559 | 1 | 0 |
| MW | g/mol | 17 | 0.0% | 18.02 | 6.643e+04 | 4169 | 78.14 | 1.606e+04 | 55.87 | 29.73 |
| RotatableBonds | count | 8 | 52.94% | 0 | 40 | 5.125 | 0 | 14.1 | 0.25 | 0 |
| TPSA | Å² | 8 | 52.94% | 0 | 111 | 30.39 | 27.15 | 36.77 | 36.6 | 19.75 |
| XLogP | dimensionless | 5 | 70.59% | -1.4 | 13.5 | 2.18 | -0.5 | 6.346 | 0.5 | 0.4 |

## `legacy_viscoelasticity` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| frequency_hz | Hz | 11 | 0.0% | 0 | 1 | 0.9091 | 1 | 0.3015 | 0 | 0 |
| loss_modulus_pa | Pa | 10 | 9.09% | 0 | 1.5e+08 | 4.011e+07 | 5e+04 | 6.575e+07 | 7.525e+07 | 5e+04 |
| storage_modulus_pa | Pa | 11 | 0.0% | 0 | 1.16e+11 | 1.136e+10 | 1e+06 | 3.473e+10 | 3e+09 | 1e+06 |
| temperature_C | °C | 11 | 0.0% | 20 | 25 | 24.09 | 25 | 2.023 | 0 | 0 |
| viscosity_mpa_s | mPa·s | 7 | 36.36% | 0.89 | 80 | 21.42 | 1.987 | 33.71 | 31.46 | 1.097 |

## `material_summary` (view)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| molecular_weight | g/mol | 23 | 0.0% | 18.02 | 6.643e+04 | 3118 | 81.38 | 1.381e+04 | 96.38 | 29.38 |

## `materials` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| molecular_weight | g/mol | 23 | 0.0% | 18.02 | 6.643e+04 | 3118 | 81.38 | 1.381e+04 | 96.38 | 29.38 |

## `mechanical_properties` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| frequency_hz | Hz | 11 | 0.0% | 0 | 1 | 0.9091 | 1 | 0.3015 | 0 | 0 |
| loss_modulus | Pa | 10 | 9.09% | 0 | 1.5e+08 | 4.011e+07 | 5e+04 | 6.575e+07 | 7.525e+07 | 5e+04 |
| storage_modulus | Pa | 11 | 0.0% | 0 | 1.16e+11 | 1.136e+10 | 1e+06 | 3.473e+10 | 3e+09 | 1e+06 |
| temperature_c | °C | 11 | 0.0% | 20 | 25 | 24.09 | 25 | 2.023 | 0 | 0 |

## `optical_dispersion` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| k | dimensionless | 650 | 76.94% | 0 | 13.78 | 0.4056 | 5.202e-05 | 1.321 | 0.0004822 | 5.193e-05 |
| n | dimensionless | 2819 | 0.0% | 0.13 | 6.709 | 1.501 | 1.474 | 0.371 | 0.09131 | 0.04676 |
| temperature_c | °C | 1569 | 44.34% | 19.85 | 25 | 20.15 | 19.85 | 1.017 | 0.25 | 0 |
| wavelength_nm | nm | 2819 | 0.0% | 191 | 3000 | 1125 | 964.5 | 648.8 | 838.4 | 392.1 |

## `physical_properties` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| density_g_cm3 | g/cm³ | 23 | 86.23% | 0.789 | 19.32 | 3.436 | 1.32 | 4.321 | 3.035 | 0.35 |
| dielectric_constant | dimensionless | 30 | 82.04% | -24 | 86 | 13.03 | 3.85 | 25.96 | 8.1 | 4.65 |
| energy_ev | eV | 114 | 31.74% | 8040 | 1.748e+04 | 1.222e+04 | 1.1e+04 | 4068 | 9352 | 2960 |
| frequency_hz | Hz | 30 | 82.04% | 0 | 3e+14 | 3e+13 | 1000 | 9.154e+13 | 1000 | 0 |
| neutron_sld | Å⁻² | 114 | 31.74% | -5.61e-07 | 5.728e-06 | 1.798e-06 | 1.411e-06 | 1.719e-06 | 3.24e-06 | 1.348e-06 |
| temperature_c | °C | 30 | 82.04% | 20 | 25 | 24.67 | 25 | 1.269 | 0 | 0 |
| wavelength_nm | nm | 117 | 29.94% | 0.07093 | 633 | 16.34 | 0.124 | 100.5 | 0.08313 | 0.03008 |
| xray_sld | Å⁻² | 114 | 31.74% | 7.556e-06 | 0.0001315 | 2.802e-05 | 1.165e-05 | 3.136e-05 | 2.457e-05 | 2.775e-06 |

## `rheology` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| shear_rate_s_inv | s⁻¹ | 0 | 100.0% | — | — | — | — | — | — | — |
| temperature_c | °C | 7 | 0.0% | 20 | 25 | 24.29 | 25 | 1.89 | 0 | 0 |
| viscosity_pas | Pa·s | 7 | 0.0% | 0.00089 | 0.08 | 0.02142 | 0.001987 | 0.03371 | 0.03146 | 0.001097 |

## `sources` (table)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| uncertainty | dimensionless | 0 | 100.0% | — | — | — | — | — | — | — |
| year | year | 0 | 100.0% | — | — | — | — | — | — | — |

## `spr_data` (view)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| eps_imag | dimensionless | 119 | 86.32% | 0 | 28.95 | 0.7566 | 4.753e-07 | 4.006 | 2.117e-06 | 3.035e-07 |
| eps_real | dimensionless | 119 | 86.32% | -40.27 | 15.26 | 0.8282 | 1.838 | 7.33 | 0.01094 | 0.006609 |
| k | dimensionless | 119 | 86.32% | 0 | 6.35 | 0.4303 | 1.753e-07 | 1.32 | 7.818e-07 | 1.177e-07 |
| n | dimensionless | 870 | 0.0% | 0.13 | 3.906 | 1.517 | 1.488 | 0.2769 | 0.1092 | 0.08457 |
| temperature_c | °C | 599 | 31.15% | 19.85 | 25 | 20.22 | 19.85 | 1.196 | 0.25 | 0 |
| wavelength_nm | nm | 870 | 0.0% | 600 | 1000 | 797.3 | 795.2 | 117 | 203.3 | 102.2 |

## `xrr_data` (view)

| Property | Units | Count | Missing% | Min | Max | Mean | Median | Std | IQR | MAD |
|----------|-------|-------|----------|-----|-----|------|--------|-----|-----|-----|
| density_g_cm3 | g/cm³ | 23 | 83.21% | 0.789 | 19.32 | 3.436 | 1.32 | 4.321 | 3.035 | 0.35 |
| energy_ev | eV | 114 | 16.79% | 8040 | 1.748e+04 | 1.222e+04 | 1.1e+04 | 4068 | 9352 | 2960 |
| neutron_sld | Å⁻² | 114 | 16.79% | -5.61e-07 | 5.728e-06 | 1.798e-06 | 1.411e-06 | 1.719e-06 | 3.24e-06 | 1.348e-06 |
| wavelength_nm | nm | 114 | 16.79% | 0.07093 | 0.1541 | 0.1128 | 0.1137 | 0.03543 | 0.08313 | 0.04041 |
| xray_sld | Å⁻² | 114 | 16.79% | 7.556e-06 | 0.0001315 | 2.802e-05 | 1.165e-05 | 3.136e-05 | 2.457e-05 | 2.775e-06 |

