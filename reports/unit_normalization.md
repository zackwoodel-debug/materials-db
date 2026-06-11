# Unit Normalization Audit

## 1. Duplicate Physical-Quantity Column Names

Columns representing the same physical quantity with different names:

| Canonical Name | Variants Found | Notes |
|---|---|---|
| `dielectric_constant` | `dielectric_real`, `real_permittivity` | eps_real is computed (generated column) in optical_dispersion; dielectric_real and real_permittivity are legacy naming variants |
| `k_extinction` | `k`, `dielectric_imag`, `imag_permittivity` | eps_imag is computed; dielectric_imag / imag_permittivity are legacy |
| `xray_sld` | `sld_xray_real`, `xray_sld_real` | word-order inversion between legacy_calculated_sld and legacy_calculated_slds |
| `neutron_sld` | `sld_neutron_real`, `neutron_sld_real` | same word-order inversion |
| `temperature` | `temperature_c`, `temperature_C` | capitalisation inconsistency across tables |
| `viscosity` | `viscosity_pas`, `viscosity_mpa_s` | viscosity_pas (SI Pa·s) vs viscosity_mpa_s (mPa·s) — 1000× scale difference |
| `storage_modulus` | `storage_modulus`, `storage_modulus_pa` | mechanical_properties uses bare `storage_modulus`; legacy uses `storage_modulus_pa` |
| `loss_modulus` | `loss_modulus`, `loss_modulus_pa` | same as above |

## 2. Value Range Survey

| Table | Column | Units | Min | Max | Suspicious? |
|---|---|---|---|---|---|
| `optical_dispersion` | `wavelength_nm` | nm | 191.0 | 3000.0 | OK |
| `optical_dispersion` | `n` | — | 0.13 | 6.709 | OK |
| `optical_dispersion` | `k` | — | 0.0 | 13.78 | OK |
| `physical_properties` | `density_g_cm3` | g/cm³ | 0.789 | 19.32 | OK |
| `physical_properties` | `dielectric_constant` | — | -24.0 | 86.0 | OK |
| `physical_properties` | `frequency_hz` | Hz | 0.0 | 300000000000000.0 | OK |
| `physical_properties` | `wavelength_nm` | nm | 0.07093 | 633.0 | OK |
| `physical_properties` | `temperature_c` | °C | 20.0 | 25.0 | OK |
| `mechanical_properties` | `frequency_hz` | Hz | 0.0 | 1.0 | OK |
| `mechanical_properties` | `temperature_c` | °C | 20.0 | 25.0 | OK |
| `rheology` | `viscosity_pas` | Pa·s | 0.0008900000000000001 | 0.08 | OK |
| `legacy_dielectric` | `frequency_hz` | Hz | 0.0 | 300000000000000.0 | OK |
| `legacy_dielectrics` | `frequency_hz` | Hz | 1000.0 | 1000.0 | OK |
| `legacy_viscoelasticity` | `frequency_hz` | Hz | 0.0 | 1.0 | OK |

## 3. Frequency Column Range Comparison Across Tables

| Table | Column | Min | Max | Distinct non-null count |
|---|---|---|---|---|
| `legacy_dielectric` | `frequency_hz` | 0.0 | 300000000000000.0 | 21 |
| `legacy_dielectrics` | `frequency_hz` | 1000.0 | 1000.0 | 9 |
| `legacy_viscoelasticity` | `frequency_hz` | 0.0 | 1.0 | 11 |
| `mechanical_properties` | `frequency_hz` | 0.0 | 1.0 | 11 |
| `rheology` | `shear_rate_s_inv` | None | None | 0 |

