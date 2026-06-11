# Spectral Validation Report
_Generated 2026-06-10 09:33_

Inter-dataset spectral comparisons and per-dataset quality flags.

## Classification key
| Class | Criterion |
|-------|-----------|
| excellent | Pearson r > 0.9999 AND nRMSE < 1% (or nRMSE < 1% for sparse) |
| warning   | r > 0.999 (or nRMSE < 5%) |
| suspicious | otherwise |

## Inter-Dataset Comparisons

### Gold (material_id=2)

| Property | Dataset A | Dataset B | WL range (nm) | Points | Pearson r | RMSE | MAE | Max dev | Class |
|----------|-----------|-----------|---------------|--------|-----------|------|-----|---------|-------|
| k | Johnson & Christy 1972; 633nm interpolated | P. B. Johnson and R. W. Christy. | 633–633 | 1 | — | 0.01676 | 0.01676 | 0.01676 | excellent |
| n | Johnson & Christy 1972; 633nm interpolated | P. B. Johnson and R. W. Christy. | 633–633 | 1 | — | 0.003443 | 0.003443 | 0.003443 | warning |

### DPPC (material_id=5)

| Property | Dataset A | Dataset B | WL range (nm) | Points | Pearson r | RMSE | MAE | Max dev | Class |
|----------|-----------|-----------|---------------|--------|-----------|------|-----|---------|-------|
| n | (unlabelled) | Chou et al. Biophys J 2010 doi:10.1016/j.bpj. | 633–633 | 1 | — | 0.002399 | 0.002399 | 0.002399 | excellent |

### PEG (material_id=9)

| Property | Dataset A | Dataset B | WL range (nm) | Points | Pearson r | RMSE | MAE | Max dev | Class |
|----------|-----------|-----------|---------------|--------|-----------|------|-----|---------|-------|
| n | (unlabelled) | Brandrup et al. Polymer Handbook 4th ed. (199 | 589–589 | 1 | — | 0.07279 | 0.07279 | 0.07279 | warning |

### TiO2 (material_id=15)

| Property | Dataset A | Dataset B | WL range (nm) | Points | Pearson r | RMSE | MAE | Max dev | Class |
|----------|-----------|-----------|---------------|--------|-----------|------|-----|---------|-------|
| k | Cauchy extrapolation from 633nm | Devore 1951 J.Opt.Soc.Am; k from thin-film ab | — | 0 | — | — | — | — | — |
| n | Cauchy extrapolation from 633nm | Devore 1951 J.Opt.Soc.Am; k from thin-film ab | — | 0 | — | — | — | — | — |

### PDMS (material_id=16)

| Property | Dataset A | Dataset B | WL range (nm) | Points | Pearson r | RMSE | MAE | Max dev | Class |
|----------|-----------|-----------|---------------|--------|-----------|------|-----|---------|-------|
| n | Cauchy extrapolation | Mark J.E. Polymer Data Handbook 4th ed 1999 | — | 0 | — | — | — | — | — |

### BSA (material_id=18)

| Property | Dataset A | Dataset B | WL range (nm) | Points | Pearson r | RMSE | MAE | Max dev | Class |
|----------|-----------|-----------|---------------|--------|-----------|------|-----|---------|-------|
| n | Cauchy extrapolation | Zhao X. et al. Langmuir 2006; protein film n | — | 0 | — | — | — | — | — |

### ITO (material_id=20)

| Property | Dataset A | Dataset B | WL range (nm) | Points | Pearson r | RMSE | MAE | Max dev | Class |
|----------|-----------|-----------|---------------|--------|-----------|------|-----|---------|-------|
| k | Kim H.K. Thin Solid Films 1999; ITO thin film | Standard sputtered ITO film; n corrected to 1 | — | 0 | — | — | — | — | — |
| n | Kim H.K. Thin Solid Films 1999; ITO thin film | Standard sputtered ITO film; n corrected to 1 | — | 0 | — | — | — | — | — |

### Chromium (material_id=21)

| Property | Dataset A | Dataset B | WL range (nm) | Points | Pearson r | RMSE | MAE | Max dev | Class |
|----------|-----------|-----------|---------------|--------|-----------|------|-----|---------|-------|
| k | Palik E.D. Handbook of Optical Constants Vol. | Palik E.D. Handbook of Optical Constants Vol. | — | 0 | — | — | — | — | — |
| n | Palik E.D. Handbook of Optical Constants Vol. | Palik E.D. Handbook of Optical Constants Vol. | — | 0 | — | — | — | — | — |

## Per-Dataset Anomaly Flags

Total anomalies: 16 (0 critical, 16 warning)

| Material | Dataset (truncated) | Property | Type | Severity | Details |
|----------|---------------------|----------|------|----------|---------|
| Gold | Johnson & Christy 1972; 633nm interpolat | wavelength | sparse_coverage | **warning** | Only 1 wavelength point(s) |
| Gold | P. B. Johnson and R. W. Christy. | wavelength | discontinuity | **warning** | Large gap(s) at indices [41, 42, 43]: [177.0, 217.0, 327.0] nm (median step=13.7 |
| DPPC | Chou et al. Biophys J 2010 doi:10.1016/j | wavelength | sparse_coverage | **warning** | Only 1 wavelength point(s) |
| PEG | Brandrup et al. Polymer Handbook 4th ed. | wavelength | sparse_coverage | **warning** | Only 1 wavelength point(s) |
| TiO2 | Cauchy extrapolation from 633nm | wavelength | sparse_coverage | **warning** | Only 2 wavelength point(s) |
| TiO2 | Devore 1951 J.Opt.Soc.Am; k from thin-fi | wavelength | sparse_coverage | **warning** | Only 1 wavelength point(s) |
| PDMS | Cauchy extrapolation | wavelength | sparse_coverage | **warning** | Only 2 wavelength point(s) |
| PDMS | Mark J.E. Polymer Data Handbook 4th ed 1 | wavelength | sparse_coverage | **warning** | Only 1 wavelength point(s) |
| PEI | Literature estimate; branched PEI bulk n | wavelength | sparse_coverage | **warning** | Only 1 wavelength point(s) |
| BSA | Cauchy extrapolation | wavelength | sparse_coverage | **warning** | Only 2 wavelength point(s) |
| BSA | Zhao X. et al. Langmuir 2006; protein fi | wavelength | sparse_coverage | **warning** | Only 1 wavelength point(s) |
| ITO | Kim H.K. Thin Solid Films 1999; ITO thin | wavelength | sparse_coverage | **warning** | Only 2 wavelength point(s) |
| ITO | Standard sputtered ITO film; n corrected | wavelength | sparse_coverage | **warning** | Only 1 wavelength point(s) |
| Chromium | Palik E.D. Handbook of Optical Constants | wavelength | sparse_coverage | **warning** | Only 2 wavelength point(s) |
| Chromium | Palik E.D. Handbook of Optical Constants | wavelength | sparse_coverage | **warning** | Only 1 wavelength point(s) |
| Silver | Johnson & Christy 1972 | wavelength | sparse_coverage | **warning** | Only 1 wavelength point(s) |

## Overall Database Statistics

| Metric | Value |
|--------|-------|
| Scalar property comparison pairs | 43 |
| Spectral comparison pairs | 12 |
| Spectral pairs with overlap | 4 |
| Spectral pairs — no overlap | 8 |
| Materials with spectral comparisons | 8 |
| Scalar excellent | 40 |
| Spectral excellent | 2 |
| Anomalies detected | 16 |
| Critical anomalies | 0 |

