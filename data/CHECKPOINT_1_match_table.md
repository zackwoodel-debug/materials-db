# CHECKPOINT 1 (v2): RI.info Match Table (50 oxides)

All 50/50 materials have >=1 match in refractiveindex.info. Every optical axis (ordinary/extraordinary, or biaxial alpha/beta/gamma) is now listed as its own row -- for a birefringent material BOTH axes are needed, not a choice between them. **Bold** dataset name = proposed default paper for that material.


## 1. Aluminium oxide / sapphire (Al2O3) -- list polymorph: corundum/sapphire

**23 materials have multiple candidate papers needing a decision (axis splits of the same paper don't count):** 1, 7, 9, 20, 23, 24, 25, 27, 29, 33, 34, 36, 37, 38, 39, 40, 42, 43, 44, 45, 46, 49, 50

- **main/Al2O3/Malitson -- Malitson and Dodge 1972: α-Al2O3 (Sapphire)** (DEFAULT)
    - `Malitson-o` axis=ordinary (o), range=0.200-5.000 um, covers 633nm: yes, dataset_label=`corundum/sapphire | Malitson1972 | o-ray` -- Malitson and Dodge 1972: α-Al2O3 (Sapphire); n(o) 0.20–5.0 µm
    - `Malitson-e` axis=extraordinary (e), range=0.200-5.000 um, covers 633nm: yes, dataset_label=`corundum/sapphire | Malitson1972 | e-ray` -- Malitson and Dodge 1972: α-Al2O3 (Sapphire); n(e) 0.20–5.0 µm
- main/Al2O3/Querry -- Querry 1985: α-Al2O3 (Sapphire)
    - `Querry-o` axis=ordinary (o), range=0.210-55.556 um, covers 633nm: yes -- Querry 1985: α-Al2O3 (Sapphire); n,k(o) 0.21–55.6 µm
    - `Querry-e` axis=extraordinary (e), range=0.210-55.556 um, covers 633nm: yes -- Querry 1985: α-Al2O3 (Sapphire); n,k(e) 0.21–55.6 µm
- main/Al2O3/Malitson -- Malitson 1962: α-Al2O3 (Sapphire)
    - `Malitson` axis=ordinary (o), range=0.265-5.577 um, covers 633nm: yes -- Malitson 1962: α-Al2O3 (Sapphire); n(o) 0.2652–5.577 µm
- main/Al2O3/Rodriguez_de_Marcos -- Rodríguez de Marcos et al. 2025: n,k 3.1e-6–993 µm
    - `Rodriguez_de_Marcos` axis=none (isotropic/cubic/amorphous), range=0.000-993.324 um, covers 633nm: yes -- Rodríguez de Marcos et al. 2025: n,k 3.1e-6–993 µm
- main/Al2O3/Boidin -- Boidin et al. 2016: n 0.3–18 µm
    - `Boidin` axis=none (isotropic/cubic/amorphous), range=0.300-18.003 um, covers 633nm: yes -- Boidin et al. 2016: n 0.3–18 µm
- main/Al2O3/Franta -- Franta et al. 2015: n,k 0.114–125 µm
    - `Franta` axis=none (isotropic/cubic/amorphous), range=0.114-125.124 um, covers 633nm: yes -- Franta et al. 2015: n,k 0.114–125 µm
- main/Al2O3/Zhukovsky -- Zhukovsky et al. 2015: n 0.211–1.69 µm
    - `Zhukovsky` axis=none (isotropic/cubic/amorphous), range=0.211-1.690 um, covers 633nm: yes -- Zhukovsky et al. 2015: n 0.211–1.69 µm
- main/Al2O3/Querry -- Querry 1985: Thin film (oxidized Al mirror)
    - `Querry` axis=none (isotropic/cubic/amorphous), range=0.210-12.500 um, covers 633nm: yes -- Querry 1985: Thin film (oxidized Al mirror); n,k 0.21–12.5 µm
- main/Al2O3/Hagemann -- Hagemann et al. 1974: n,k 0.000775–0.207 µm
    - `Hagemann` axis=none (isotropic/cubic/amorphous), range=0.001-0.207 um, covers 633nm: no -- Hagemann et al. 1974: n,k 0.000775–0.207 µm
- main/Al2O3/Kischkat -- Kischkat et al. 2012: n,k 1.54–14.3 µm
    - `Kischkat` axis=none (isotropic/cubic/amorphous), range=1.539-14.286 um, covers 633nm: no -- Kischkat et al. 2012: n,k 1.54–14.3 µm


## 2. Beryllium oxide (BeO)
- **main/BeO/Edwards -- Edwards and White 1991:  0.44–7.0 µm** (DEFAULT)
    - `Edwards-o` axis=ordinary (o), range=0.440-7.000 um, covers 633nm: yes, dataset_label=`Edwards1991 | o-ray` -- Edwards and White 1991: n(o) 0.44–7.0 µm
    - `Edwards-e` axis=extraordinary (e), range=0.440-7.000 um, covers 633nm: yes, dataset_label=`Edwards1991 | e-ray` -- Edwards and White 1991: n(e) 0.44–7.0 µm


## 3. Chrysoberyl (BeAl2O4) -- list polymorph: chrysoberyl
- **main/BeAl2O4/Walling -- Walling et al. 1980:  0.25–2.6 µm** (DEFAULT)
    - `Walling-α` axis=biaxial alpha (nα), range=0.250-2.600 um, covers 633nm: yes, dataset_label=`chrysoberyl | Walling1980 | alpha-axis` -- Walling et al. 1980: n(α) 0.25–2.6 µm
    - `Walling-β` axis=biaxial beta (nβ), range=0.250-2.600 um, covers 633nm: yes, dataset_label=`chrysoberyl | Walling1980 | beta-axis` -- Walling et al. 1980: n(β) 0.25–2.6 µm
    - `Walling-γ` axis=biaxial gamma (nγ), range=0.250-2.600 um, covers 633nm: yes, dataset_label=`chrysoberyl | Walling1980 | gamma-axis` -- Walling et al. 1980: n(γ) 0.25–2.6 µm


## 4. Beryllium hexaaluminate (BeAl6O10)
- **main/BeAl6O10/Pestryakov -- Pestryakov et al. 1997:  0.43–1.1 µm** (DEFAULT)
    - `Pestryakov-α` axis=biaxial alpha (nα), range=0.430-1.100 um, covers 633nm: yes, dataset_label=`Pestryakov1997 | alpha-axis` -- Pestryakov et al. 1997: n(α) 0.43–1.1 µm
    - `Pestryakov-β` axis=biaxial beta (nβ), range=0.430-1.100 um, covers 633nm: yes, dataset_label=`Pestryakov1997 | beta-axis` -- Pestryakov et al. 1997: n(β) 0.43–1.1 µm
    - `Pestryakov-γ` axis=biaxial gamma (nγ), range=0.430-1.100 um, covers 633nm: yes, dataset_label=`Pestryakov1997 | gamma-axis` -- Pestryakov et al. 1997: n(γ) 0.43–1.1 µm


## 5. Calcium gadolinium aluminate (CaGdAlO4)
- **main/CaGdAlO4/Loiko -- Loiko et al. 2017:  0.35–2.1 µm** (DEFAULT)
    - `Loiko-o` axis=ordinary (o), range=0.350-2.100 um, covers 633nm: yes, dataset_label=`K2NiF4-type | Loiko2017 | o-ray` -- Loiko et al. 2017: n(o) 0.35–2.1 µm
    - `Loiko-e` axis=extraordinary (e), range=0.350-2.100 um, covers 633nm: yes, dataset_label=`K2NiF4-type | Loiko2017 | e-ray` -- Loiko et al. 2017: n(e) 0.35–2.1 µm


## 6. Calcium yttrium aluminate (CaYAlO4)
- **main/CaYAlO4/Loiko -- Loiko et al. 2017:  0.35–2.1 µm** (DEFAULT)
    - `Loiko-o` axis=ordinary (o), range=0.350-2.100 um, covers 633nm: yes, dataset_label=`K2NiF4-type | Loiko2017 | o-ray` -- Loiko et al. 2017: n(o) 0.35–2.1 µm
    - `Loiko-e` axis=extraordinary (e), range=0.350-2.100 um, covers 633nm: yes, dataset_label=`K2NiF4-type | Loiko2017 | e-ray` -- Loiko et al. 2017: n(e) 0.35–2.1 µm


## 7. Spinel (MgAl2O4) -- list polymorph: spinel
- **main/MgAl2O4/Tropf -- Tropf and Thomas 1991: n 0.35–5.5 µm** (DEFAULT)
    - `Tropf` axis=none (isotropic/cubic/amorphous), range=0.350-5.500 um, covers 633nm: yes, dataset_label=`spinel | Tropf1991` -- Tropf and Thomas 1991: n 0.35–5.5 µm
- main/MgAl2O4/Chernova -- Chernova et al. 2017: n,k 0.14–1.67 µm
    - `Chernova` axis=none (isotropic/cubic/amorphous), range=0.141-1.675 um, covers 633nm: yes -- Chernova et al. 2017: n,k 0.14–1.67 µm


## 8. Lanthanum aluminate (LaAlO3)
- **main/LaAlO3/Chernova -- Chernova et al. 2017: n,k 0.14–1.67 µm** (DEFAULT)
    - `Chernova` axis=none (isotropic/cubic/amorphous), range=0.141-1.675 um, covers 633nm: yes, dataset_label=`Chernova2017` -- Chernova et al. 2017: n,k 0.14–1.67 µm


## 9. Barium borate (BBO) (BaB2O4) -- list polymorph: beta-BBO
- **main/BaB2O4/Eimerl -- Eimerl et al. 1987:  0.22–1.06 µm** (DEFAULT)
    - `Eimerl-o` axis=ordinary (o), range=0.220-1.060 um, covers 633nm: yes, dataset_label=`beta-BBO | Eimerl1987 | o-ray` -- Eimerl et al. 1987: n(o) 0.22–1.06 µm
    - `Eimerl-e` axis=extraordinary (e), range=0.220-1.060 um, covers 633nm: yes, dataset_label=`beta-BBO | Eimerl1987 | e-ray` -- Eimerl et al. 1987: n(e) 0.22–1.06 µm
- main/BaB2O4/Tamosauskas -- Tamošauskas et al. 2018: ,k 0.188–5.2 µm
    - `Tamosauskas-o` axis=ordinary (o), range=0.188-5.200 um, covers 633nm: yes -- Tamošauskas et al. 2018: n(o),k 0.188–5.2 µm
    - `Tamosauskas-e` axis=extraordinary (e), range=0.188-5.200 um, covers 633nm: yes -- Tamošauskas et al. 2018: n(e),k 0.188–5.2 µm
- main/BaB2O4/Zhang -- Zhang et al. 2000:  0.64–3.18 µm
    - `Zhang-o` axis=ordinary (o), range=0.640-3.180 um, covers 633nm: no -- Zhang et al. 2000: n(o) 0.64–3.18 µm
    - `Zhang-e` axis=extraordinary (e), range=0.640-3.180 um, covers 633nm: no -- Zhang et al. 2000: n(e) 0.64–3.18 µm


## 10. Bismuth triborate (BiBO) (BiB3O6)
- **main/BiB3O6/Umemura -- Umemura et al. 2007:  0.48–3.1 µm** (DEFAULT)
    - `Umemura-α` axis=biaxial alpha (nα), range=0.480-3.100 um, covers 633nm: yes, dataset_label=`alpha-BiBO | Umemura2007 | alpha-axis` -- Umemura et al. 2007: n(α) 0.48–3.1 µm
    - `Umemura-β` axis=biaxial beta (nβ), range=0.480-3.100 um, covers 633nm: yes, dataset_label=`alpha-BiBO | Umemura2007 | beta-axis` -- Umemura et al. 2007: n(β) 0.48–3.1 µm
    - `Umemura-γ` axis=biaxial gamma (nγ), range=0.480-3.100 um, covers 633nm: yes, dataset_label=`alpha-BiBO | Umemura2007 | gamma-axis` -- Umemura et al. 2007: n(γ) 0.48–3.1 µm


## 11. Lithium triborate (LBO) (LiB3O5)
- **main/LiB3O5/Chen -- Chen et al. 1989:  0.289–1.06 µm** (DEFAULT)
    - `Chen-α` axis=biaxial alpha (nα), range=0.289-1.064 um, covers 633nm: yes, dataset_label=`Chen1989 | alpha-axis` -- Chen et al. 1989: n(α) 0.289–1.06 µm
    - `Chen-β` axis=biaxial beta (nβ), range=0.289-1.064 um, covers 633nm: yes, dataset_label=`Chen1989 | beta-axis` -- Chen et al. 1989: n(β) 0.289–1.06 µm
    - `Chen-γ` axis=biaxial gamma (nγ), range=0.289-1.064 um, covers 633nm: yes, dataset_label=`Chen1989 | gamma-axis` -- Chen et al. 1989: n(γ) 0.289–1.06 µm


## 12. Cesium lithium borate (CLBO) (CsLiB6O10)
- **main/CsLiB6O10/Sasaki -- Sasaki et al. 2003:  0.19–2.75 µm** (DEFAULT)
    - `Sasaki-o` axis=ordinary (o), range=0.190-2.750 um, covers 633nm: yes, dataset_label=`Sasaki2003 | o-ray` -- Sasaki et al. 2003: n(o) 0.19–2.75 µm
    - `Sasaki-e` axis=extraordinary (e), range=0.190-2.750 um, covers 633nm: yes, dataset_label=`Sasaki2003 | e-ray` -- Sasaki et al. 2003: n(e) 0.19–2.75 µm


## 13. Lutetium aluminium borate (LuAl3(BO3)4)
- **main/LuAl3_BO3_4/Fang -- Fang et al. 2013:  0.266–1.34 µm** (DEFAULT)
    - `Fang-o` axis=ordinary (o), range=0.266-1.338 um, covers 633nm: yes, dataset_label=`Fang2013 | o-ray` -- Fang et al. 2013: n(o) 0.266–1.34 µm
    - `Fang-e` axis=extraordinary (e), range=0.266-1.338 um, covers 633nm: yes, dataset_label=`Fang2013 | e-ray` -- Fang et al. 2013: n(e) 0.266–1.34 µm


## 14. Calcite (CaCO3) -- list polymorph: calcite
- **main/CaCO3/Ghosh -- Ghosh 1999:  0.204–2.172 µm** (DEFAULT)
    - `Ghosh-o` axis=ordinary (o), range=0.204-2.172 um, covers 633nm: yes, dataset_label=`calcite | Ghosh1999 | o-ray` -- Ghosh 1999: n(o) 0.204–2.172 µm
    - `Ghosh-e` axis=extraordinary (e), range=0.204-2.172 um, covers 633nm: yes, dataset_label=`calcite | Ghosh1999 | e-ray` -- Ghosh 1999: n(e) 0.204–2.172 µm


## 15. Copper(II) oxide (CuO)
- **main/CuO/Brimhall -- Brimhall et al. 2009: n,k 0.0101–0.0348 µm** (DEFAULT)
    - `Brimhall` axis=none (isotropic/cubic/amorphous), range=0.010-0.035 um, covers 633nm: no, dataset_label=`Brimhall2009` -- Brimhall et al. 2009: n,k 0.0101–0.0348 µm


## 16. Copper(I) oxide (Cu2O)
- **main/Cu2O/Querry -- Querry 1985: n,k 2.5–55.6 µm** (DEFAULT)
    - `Querry` axis=none (isotropic/cubic/amorphous), range=2.500-55.556 um, covers 633nm: no, dataset_label=`Querry1985` -- Querry 1985: n,k 2.5–55.6 µm


## 17. Dysprosium oxide (Dy2O3)
- **main/Dy2O3/Medenbach -- Medenbach et al. 2001: n 0.435–0.644 µm** (DEFAULT)
    - `Medenbach` axis=none (isotropic/cubic/amorphous), range=0.435-0.644 um, covers 633nm: yes, dataset_label=`Medenbach2001` -- Medenbach et al. 2001: n 0.435–0.644 µm


## 18. Hematite (Fe2O3) -- list polymorph: hematite
- **main/Fe2O3/Querry -- Querry 1985: α-Fe2O3 (Hematite)** (DEFAULT)
    - `Querry-o` axis=ordinary (o), range=0.210-90.909 um, covers 633nm: yes, dataset_label=`hematite | Querry1985 | o-ray` -- Querry 1985: α-Fe2O3 (Hematite); n,k(o) 0.21–55.6 µm
    - `Querry-e` axis=extraordinary (e), range=0.210-55.556 um, covers 633nm: yes, dataset_label=`hematite | Querry1985 | e-ray` -- Querry 1985: α-Fe2O3 (Hematite); n,k(e) 0.21–55.6 µm


## 19. Magnetite (Fe3O4) -- list polymorph: magnetite
- **main/Fe3O4/Querry -- Querry 1985: n,k 0.21–55.6 µm** (DEFAULT)
    - `Querry` axis=none (isotropic/cubic/amorphous), range=0.210-55.556 um, covers 633nm: yes, dataset_label=`magnetite | Querry1985` -- Querry 1985: n,k 0.21–55.6 µm


## 20. Germanium dioxide (GeO2)
- **main/GeO2/Fleming -- Fleming 1984: Fused germania** (DEFAULT)
    - `Fleming` axis=none (isotropic/cubic/amorphous), range=0.360-4.300 um, covers 633nm: yes, dataset_label=`Fleming1984` -- Fleming 1984: Fused germania; n 0.36–4.3 µm
- main/GeO2/Nunley -- Nunley et al, 2016: n,k 0.188–2.48 µm
    - `Nunley` axis=none (isotropic/cubic/amorphous), range=0.188-2.480 um, covers 633nm: yes -- Nunley et al, 2016: n,k 0.188–2.48 µm


## 21. Bismuth germanate (Bi12GeO20) -- list polymorph: BGO
- **main/Bi12GeO20/Simon -- Simon et al. 1997: n 0.45–0.70 µm** (DEFAULT)
    - `Simon` axis=none (isotropic/cubic/amorphous), range=0.450-0.700 um, covers 633nm: yes, dataset_label=`BGO | Simon1997` -- Simon et al. 1997: n 0.45–0.70 µm


## 22. Lead germanate (Pb5Ge3O11)
- **main/Pb5Ge3O11/Simon -- Simon et al. 1997:  0.45–0.70 µm** (DEFAULT)
    - `Simon-o` axis=ordinary (o), range=0.450-0.700 um, covers 633nm: yes, dataset_label=`Simon1997 | o-ray` -- Simon et al. 1997: n(o) 0.45–0.70 µm
    - `Simon-e` axis=extraordinary (e), range=0.450-0.700 um, covers 633nm: yes, dataset_label=`Simon1997 | e-ray` -- Simon et al. 1997: n(e) 0.45–0.70 µm


## 23. Hafnium dioxide (HfO2)
- **main/HfO2/Al-Kuhaili -- Al-Kuhaili 2004: n 0.2–2.0 µm** (DEFAULT)
    - `Al-Kuhaili` axis=none (isotropic/cubic/amorphous), range=0.200-2.000 um, covers 633nm: yes, dataset_label=`Al2004` -- Al-Kuhaili 2004: n 0.2–2.0 µm
- main/HfO2/Franta -- Franta et al. 2015: n,k 0.115–125 µm
    - `Franta` axis=none (isotropic/cubic/amorphous), range=0.115-125.124 um, covers 633nm: yes -- Franta et al. 2015: n,k 0.115–125 µm
- main/HfO2/Bright -- Bright et al. 2012: n,k 0.385–500 µm
    - `Bright` axis=none (isotropic/cubic/amorphous), range=0.385-500.000 um, covers 633nm: yes -- Bright et al. 2012: n,k 0.385–500 µm
- main/HfO2/Siefke -- Siefke et al. 2026: Thin film
    - `Siefke` axis=none (isotropic/cubic/amorphous), range=0.124-0.620 um, covers 633nm: no -- Siefke et al. 2026: Thin film; n,k 0.124–0.620 µm


## 24. Lithium iodate (LiIO3)
- **main/LiIO3/Umegaki -- Umegaki et al. 1971:  0.4–5.7 µm** (DEFAULT)
    - `Umegaki-o` axis=ordinary (o), range=0.400-5.700 um, covers 633nm: yes, dataset_label=`Umegaki1971 | o-ray` -- Umegaki et al. 1971: n(o) 0.4–5.7 µm
    - `Umegaki-e` axis=extraordinary (e), range=0.400-5.700 um, covers 633nm: yes, dataset_label=`Umegaki1971 | e-ray` -- Umegaki et al. 1971: n(e) 0.4–5.7 µm
- main/LiIO3/Herbst -- Herbst 1976:  0.546–5.0 µm
    - `Herbst-o` axis=ordinary (o), range=0.546-5.000 um, covers 633nm: yes -- Herbst 1976: n(o) 0.546–5.0 µm
    - `Herbst-e` axis=extraordinary (e), range=0.546-5.000 um, covers 633nm: yes -- Herbst 1976: n(e) 0.546–5.0 µm


## 25. Lutetium oxide (Lu2O3)
- **main/Lu2O3/Medenbach -- Medenbach et al. 2001: n 0.435–0.644 µm** (DEFAULT)
    - `Medenbach` axis=none (isotropic/cubic/amorphous), range=0.435-0.644 um, covers 633nm: yes, dataset_label=`Medenbach2001` -- Medenbach et al. 2001: n 0.435–0.644 µm
- main/Lu2O3/Yao -- Yao et al. 2022: n 0.210–1.69 µm, k 0.210–0.224 µm
    - `Yao` axis=none (isotropic/cubic/amorphous), range=0.210-1.690 um, covers 633nm: yes -- Yao et al. 2022: n 0.210–1.69 µm, k 0.210–0.224 µm
- main/Lu2O3/Kaminskii -- Kaminskii et al. 2008: n 0.365–2.325 µm
    - `Kaminskii` axis=none (isotropic/cubic/amorphous), range=0.365-2.325 um, covers 633nm: yes -- Kaminskii et al. 2008: n 0.365–2.325 µm


## 26. LuAG (Lu3Al5O12) -- list polymorph: garnet
- **main/Lu3Al5O12/Hrabovsky -- Hrabovský et al. 2021: n 0.193–1.69 µm** (DEFAULT)
    - `Hrabovsky` axis=none (isotropic/cubic/amorphous), range=0.193-1.690 um, covers 633nm: yes, dataset_label=`garnet | Hrabovsky2021` -- Hrabovský et al. 2021: n 0.193–1.69 µm


## 27. Magnesium oxide (MgO)
- **main/MgO/Stephens -- Stephens and Malitson 1952: n 0.36–5.4 µm** (DEFAULT)
    - `Stephens` axis=none (isotropic/cubic/amorphous), range=0.360-5.400 um, covers 633nm: yes, dataset_label=`Stephens1952` -- Stephens and Malitson 1952: n 0.36–5.4 µm
- main/MgO/Stephens-vis -- Stephens and Malitson 1952: n 0.405–0.768 µm
    - `Stephens-vis` axis=none (isotropic/cubic/amorphous), range=0.405-0.768 um, covers 633nm: yes -- Stephens and Malitson 1952: n 0.405–0.768 µm
- main/MgO/Synowicki -- Synowicki and Tiwald 2004: n,k 0.13–33 µm
    - `Synowicki` axis=none (isotropic/cubic/amorphous), range=0.130-33.000 um, covers 633nm: yes -- Synowicki and Tiwald 2004: n,k 0.13–33 µm


## 28. Molybdenum dioxide (MoO2)
- **main/MoO2/Ganzhinov -- Ganzhinov et al. 2026: Thin film** (DEFAULT)
    - `Ganzhinov` axis=none (isotropic/cubic/amorphous), range=0.191-1.688 um, covers 633nm: yes, dataset_label=`Ganzhinov2026` -- Ganzhinov et al. 2026: Thin film; n,k 0.191–1.69 µm


## 29. Molybdenum trioxide (MoO3)
- **main/MoO3/Lajaunie -- Lajaunie et al. 2013:  0.019–24.8 µm** (DEFAULT)
    - `Lajaunie-α` axis=biaxial alpha (nα), range=0.019-24.797 um, covers 633nm: yes, dataset_label=`Lajaunie2013 | alpha-axis` -- Lajaunie et al. 2013: n,k(α) 0.019–24.8 µm
    - `Lajaunie-β` axis=biaxial beta (nβ), range=0.019-24.797 um, covers 633nm: yes, dataset_label=`Lajaunie2013 | beta-axis` -- Lajaunie et al. 2013: n,k(β) 0.019–24.8 µm
    - `Lajaunie-γ` axis=biaxial gamma (nγ), range=0.019-24.797 um, covers 633nm: yes, dataset_label=`Lajaunie2013 | gamma-axis` -- Lajaunie et al. 2013: n,k(γ) 0.019–24.8 µm
- main/MoO3/Vos -- Vos et al. 2016: Thin film
    - `Vos` axis=none (isotropic/cubic/amorphous), range=0.191-0.999 um, covers 633nm: yes -- Vos et al. 2016: Thin film; n,k 0.019–1 µm
- main/MoO3/Stelling -- Stelling et al. 2017: Thin film
    - `Stelling` axis=none (isotropic/cubic/amorphous), range=0.301-0.899 um, covers 633nm: yes -- Stelling et al. 2017: Thin film; n,k 0.301–0.899 µm


## 30. Calcium molybdate (CaMoO4)
- **main/CaMoO4/Bond -- Bond 1965:  0.45–3.8 µm** (DEFAULT)
    - `Bond-o` axis=ordinary (o), range=0.450-3.800 um, covers 633nm: yes, dataset_label=`Bond1965 | o-ray` -- Bond 1965: n(o) 0.45–3.8 µm
    - `Bond-e` axis=extraordinary (e), range=0.450-3.800 um, covers 633nm: yes, dataset_label=`Bond1965 | e-ray` -- Bond 1965: n(e) 0.45–3.8 µm


## 31. Lead molybdate (PbMoO4)
- **main/PbMoO4/Malitson -- Malitson 1978:  0.44–1.08 µm** (DEFAULT)
    - `Malitson-o` axis=ordinary (o), range=0.440-1.080 um, covers 633nm: yes, dataset_label=`Malitson1978 | o-ray` -- Malitson 1978: n(o) 0.44–1.08 µm
    - `Malitson-e` axis=extraordinary (e), range=0.440-1.080 um, covers 633nm: yes, dataset_label=`Malitson1978 | e-ray` -- Malitson 1978: n(e) 0.44–1.08 µm


## 32. Strontium molybdate (SrMoO4)
- **main/SrMoO4/Bond -- Bond 1965:  0.45–2.4 µm** (DEFAULT)
    - `Bond-o` axis=ordinary (o), range=0.450-2.400 um, covers 633nm: yes, dataset_label=`Bond1965 | o-ray` -- Bond 1965: n(o) 0.45–2.4 µm
    - `Bond-e` axis=extraordinary (e), range=0.450-2.400 um, covers 633nm: yes, dataset_label=`Bond1965 | e-ray` -- Bond 1965: n(e) 0.45–2.4 µm


## 33. Niobium pentoxide (Nb2O5)
- **main/Nb2O5/Franta -- Franta et al. 2024: n,k 0.120–399 µm** (DEFAULT)
    - `Franta` axis=none (isotropic/cubic/amorphous), range=0.120-399.362 um, covers 633nm: yes, dataset_label=`amorphous | Franta2024` -- Franta et al. 2024: n,k 0.120–399 µm
- main/Nb2O5/Lemarchand -- Lemarchand 2013: n,k 0.25–2.5 µm
    - `Lemarchand` axis=none (isotropic/cubic/amorphous), range=0.250-2.500 um, covers 633nm: yes -- Lemarchand 2013: n,k 0.25–2.5 µm
- main/Nb2O5/Horcholle-400 -- Horcholle et al. 2022: Thin film annealed at 400 °C
    - `Horcholle-400` axis=none (isotropic/cubic/amorphous), range=0.207-0.827 um, covers 633nm: yes -- Horcholle et al. 2022: Thin film annealed at 400 °C; n,k 0.207–0.827 µm
- main/Nb2O5/Horcholle-800 -- Horcholle et al. 2022: Thin film annealed at 800 °C
    - `Horcholle-800` axis=none (isotropic/cubic/amorphous), range=0.207-0.827 um, covers 633nm: yes -- Horcholle et al. 2022: Thin film annealed at 800 °C; n,k 0.207–0.827 µm


## 34. Potassium niobate (KNbO3)
- **main/KNbO3/Zysset -- Zysset et al. 1992:  0.40–3.4 µm** (DEFAULT)
    - `Zysset-α` axis=biaxial alpha (nα), range=0.400-3.400 um, covers 633nm: yes, dataset_label=`Zysset1992 | alpha-axis` -- Zysset et al. 1992: n(α) 0.40–3.4 µm
    - `Zysset-β` axis=biaxial beta (nβ), range=0.400-3.400 um, covers 633nm: yes, dataset_label=`Zysset1992 | beta-axis` -- Zysset et al. 1992: n(β) 0.40–3.4 µm
    - `Zysset-γ` axis=biaxial gamma (nγ), range=0.400-3.400 um, covers 633nm: yes, dataset_label=`Zysset1992 | gamma-axis` -- Zysset et al. 1992: n(γ) 0.40–3.4 µm
- main/KNbO3/Umemura -- Umemura et al. 1999:  0.40–5.3 µm
    - `Umemura-α` axis=biaxial alpha (nα), range=0.400-5.300 um, covers 633nm: yes -- Umemura et al. 1999: n(α) 0.40–5.3 µm
    - `Umemura-β` axis=biaxial beta (nβ), range=0.400-5.300 um, covers 633nm: yes -- Umemura et al. 1999: n(β) 0.40–5.3 µm
    - `Umemura-γ` axis=biaxial gamma (nγ), range=0.400-5.300 um, covers 633nm: yes -- Umemura et al. 1999: n(γ) 0.40–5.3 µm


## 35. Lithium niobate (LiNbO3)
- **main/LiNbO3/Zelmon -- Zelmon et al. 1997:  0.4–5.0 µm** (DEFAULT)
    - `Zelmon-o` axis=ordinary (o), range=0.400-5.000 um, covers 633nm: yes, dataset_label=`Zelmon1997 | o-ray` -- Zelmon et al. 1997: n(o) 0.4–5.0 µm
    - `Zelmon-e` axis=extraordinary (e), range=0.400-5.000 um, covers 633nm: yes, dataset_label=`Zelmon1997 | e-ray` -- Zelmon et al. 1997: n(e) 0.4–5.0 µm


## 36. Scandium oxide (Sc2O3)
- **main/Sc2O3/Medenbach -- Medenbach et al. 2001: n 0.435–0.644 µm** (DEFAULT)
    - `Medenbach` axis=none (isotropic/cubic/amorphous), range=0.435-0.644 um, covers 633nm: yes, dataset_label=`Medenbach2001` -- Medenbach et al. 2001: n 0.435–0.644 µm
- main/Sc2O3/Belosludtsev -- Belosludtsev et al. 2018: n,k 0.270–1.200 µm
    - `Belosludtsev` axis=none (isotropic/cubic/amorphous), range=0.230-1.200 um, covers 633nm: yes -- Belosludtsev et al. 2018: n,k 0.270–1.200 µm
- main/Sc2O3/Arndt -- Arndt et al. 1984: n 0.40–0.75 µm
    - `Arndt` axis=none (isotropic/cubic/amorphous), range=0.400-0.750 um, covers 633nm: yes -- Arndt et al. 1984: n 0.40–0.75 µm


## 37. Silicon monoxide (SiO) -- list polymorph: amorphous
- **main/SiO/Hass -- Hass and Salzberg 1954: n,k 0.24–14.0 µm** (DEFAULT)
    - `Hass` axis=none (isotropic/cubic/amorphous), range=0.240-14.000 um, covers 633nm: yes, dataset_label=`amorphous | Hass1954` -- Hass and Salzberg 1954: n,k 0.24–14.0 µm
- main/SiO/Herguedas -- Herguedas and Carretero 2023: n,k 5.0–25 µm
    - `Herguedas` axis=none (isotropic/cubic/amorphous), range=5.000-25.000 um, covers 633nm: no -- Herguedas and Carretero 2023: n,k 5.0–25 µm
- main/SiO/Fernandez-Perea -- Fernandez-Perea et al. 2009: n,k 0.00155–0.177 µm
    - `Fernandez-Perea` axis=none (isotropic/cubic/amorphous), range=0.002-0.177 um, covers 633nm: no -- Fernandez-Perea et al. 2009: n,k 0.00155–0.177 µm
- Excluded as non-matching stoichiometry: Herguedas-SiO0.31, Herguedas-SiO0.61, Herguedas-SiO1.10, Herguedas-SiO1.71, Herguedas-SiO1.89, Herguedas-SiO1.92


## 38. Silicon dioxide / quartz (SiO2) -- list polymorph: alpha-quartz
- **main/SiO2/Malitson -- Malitson 1965: n 0.21–6.7 µm** (DEFAULT)
    - `Malitson` axis=none (isotropic/cubic/amorphous), range=0.210-6.700 um, covers 633nm: yes, dataset_label=`amorphous | Malitson1965` -- Malitson 1965: n 0.21–6.7 µm
- main/SiO2/Ghosh -- Ghosh 1999: α-Quartz,  0.198–2.05 µm
    - `Ghosh-o` axis=ordinary (o), range=0.198-2.053 um, covers 633nm: yes -- Ghosh 1999: α-Quartz, n(o) 0.198–2.05 µm
    - `Ghosh-e` axis=extraordinary (e), range=0.198-2.053 um, covers 633nm: yes -- Ghosh 1999: α-Quartz, n(e) 0.198–2.05 µm
- main/SiO2/Radhakrishnan -- Radhakrishnan 1951: α-Quartz
    - `Radhakrishnan-o` axis=ordinary (o), range=0.180-3.000 um, covers 633nm: yes -- Radhakrishnan 1951: α-Quartz; n(o) 0.18–3 µm
    - `Radhakrishnan-e` axis=extraordinary (e), range=0.180-3.000 um, covers 633nm: yes -- Radhakrishnan 1951: α-Quartz; n(e) 0.18–3 µm
- main/SiO2/Arosa -- Arosa and de la Fuente 2020: n 0.26–1.7 µm
    - `Arosa` axis=none (isotropic/cubic/amorphous), range=0.260-1.700 um, covers 633nm: yes -- Arosa and de la Fuente 2020: n 0.26–1.7 µm
- main/SiO2/Franta -- Franta et al. 2016: n,k 0.0248–125 µm
    - `Franta` axis=none (isotropic/cubic/amorphous), range=0.025-125.141 um, covers 633nm: yes -- Franta et al. 2016: n,k 0.0248–125 µm
- main/SiO2/Rodriguez-de_Marcos -- Rodríguez-de Marcos et al. 2016: n,k 0.03–1.5 µm
    - `Rodriguez-de_Marcos` axis=none (isotropic/cubic/amorphous), range=0.030-1.511 um, covers 633nm: yes -- Rodríguez-de Marcos et al. 2016: n,k 0.03–1.5 µm
- main/SiO2/Franta-25C -- Franta et al. 2016: n,k 0.0275–125 µm; 25 °C
    - `Franta-25C` axis=none (isotropic/cubic/amorphous), range=0.028-125.141 um, covers 633nm: yes -- Franta et al. 2016: n,k 0.0275–125 µm; 25 °C
- main/SiO2/Franta-300C -- Franta et al. 2016: n,k 0.0275–125 µm; 300 °C
    - `Franta-300C` axis=none (isotropic/cubic/amorphous), range=0.028-125.141 um, covers 633nm: yes -- Franta et al. 2016: n,k 0.0275–125 µm; 300 °C
- main/SiO2/Gao -- Gao et al. 2013: n,k 0.252–1.25 µm
    - `Gao` axis=none (isotropic/cubic/amorphous), range=0.252-1.250 um, covers 633nm: yes -- Gao et al. 2013: n,k 0.252–1.25 µm
- main/SiO2/Lemarchand -- Lemarchand 2013: n,k 0.25–2.5 µm
    - `Lemarchand` axis=none (isotropic/cubic/amorphous), range=0.250-2.500 um, covers 633nm: yes -- Lemarchand 2013: n,k 0.25–2.5 µm
- main/SiO2/Nyakuchena -- Nyakuchena et al. 2023: n 1.10–1.65 µm
    - `Nyakuchena` axis=none (isotropic/cubic/amorphous), range=1.100-1.650 um, covers 633nm: no -- Nyakuchena et al. 2023: n 1.10–1.65 µm
- main/SiO2/Popova -- Popova et al. 1972: n,k 7–50 µm
    - `Popova` axis=none (isotropic/cubic/amorphous), range=7.000-50.000 um, covers 633nm: no -- Popova et al. 1972: n,k 7–50 µm
- main/SiO2/Kischkat -- Kischkat et al. 2012: n,k 1.54–14.3 µm
    - `Kischkat` axis=none (isotropic/cubic/amorphous), range=1.538-14.286 um, covers 633nm: no -- Kischkat et al. 2012: n,k 1.54–14.3 µm
- main/SiO2/Herguedas -- Herguedas and Carretero 2023: n,k 5.0–25 µm
    - `Herguedas` axis=none (isotropic/cubic/amorphous), range=5.000-25.000 um, covers 633nm: no -- Herguedas and Carretero 2023: n,k 5.0–25 µm


## 39. Tantalum pentoxide (Ta2O5)
- **main/Ta2O5/Bright-amorphous -- Bright et al. 2013: n,k 0.5–1000 µm** (DEFAULT)
    - `Bright-amorphous` axis=none (isotropic/cubic/amorphous), range=0.500-1000.000 um, covers 633nm: yes, dataset_label=`Bright2013` -- Bright et al. 2013: n,k 0.5–1000 µm
- main/Ta2O5/Cheikh-amorphous-3.28-4-25 -- Cheikh et al. 2025: Power 3.28, O2 4, As deposited
    - `Cheikh-amorphous-3.28-4-25` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 3.28, O2 4, As deposited; n,k 0.207–1.24 µm
- main/Ta2O5/Cheikh-amorphous-3.28-8-25 -- Cheikh et al. 2025: Power 3.28, O2 8, As deposited
    - `Cheikh-amorphous-3.28-8-25` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 3.28, O2 8, As deposited; n,k 0.207–1.24 µm
- main/Ta2O5/Cheikh-amorphous-3.28-12-25 -- Cheikh et al. 2025: Power 3.28, O2 12, As deposited
    - `Cheikh-amorphous-3.28-12-25` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 3.28, O2 12, As deposited; n,k 0.207–1.24 µm
- main/Ta2O5/Cheikh-amorphous-3.28-16-25 -- Cheikh et al. 2025: Power 3.28, O2 16, As deposited
    - `Cheikh-amorphous-3.28-16-25` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 3.28, O2 16, As deposited; n,k 0.207–1.24 µm
- main/Ta2O5/Cheikh-amorphous-4.38-12-25 -- Cheikh et al. 2025: Power 4.38, O2 12, As deposited
    - `Cheikh-amorphous-4.38-12-25` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 4.38, O2 12, As deposited; n,k 0.207–1.24 µm
- main/Ta2O5/Cheikh-amorphous-5.48-12-25 -- Cheikh et al. 2025: Power 5.48, O2 12, As deposited
    - `Cheikh-amorphous-5.48-12-25` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 5.48, O2 12, As deposited; n,k 0.207–1.24 µm
- main/Ta2O5/Cheikh-amorphous-6.75-12-25 -- Cheikh et al. 2025: Power 6.75, O2 12, As deposited
    - `Cheikh-amorphous-6.75-12-25` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 6.75, O2 12, As deposited; n,k 0.207–1.24 µm
- main/Ta2O5/Cheikh-amorphous-3.28-8-450 -- Cheikh et al. 2025: Power 3.28, O2 8, Anneal. 450
    - `Cheikh-amorphous-3.28-8-450` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 3.28, O2 8, Anneal. 450; n,k 0.207–1.24 µm
- main/Ta2O5/Cheikh-amorphous-3.28-8-550 -- Cheikh et al. 2025: Power 3.28, O2 8, Anneal. 550
    - `Cheikh-amorphous-3.28-8-550` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 3.28, O2 8, Anneal. 550; n,k 0.207–1.24 µm
- main/Ta2O5/Rodriguez-de_Marcos -- Rodríguez-de Marcos et al. 2016: n,k 0.03–1.5 µm
    - `Rodriguez-de_Marcos` axis=none (isotropic/cubic/amorphous), range=0.029-1.514 um, covers 633nm: yes -- Rodríguez-de Marcos et al. 2016: n,k 0.03–1.5 µm
- main/Ta2O5/Franta-2015 -- Franta et al. 2015: n,k 0.142–125 µm
    - `Franta-2015` axis=none (isotropic/cubic/amorphous), range=0.142-125.124 um, covers 633nm: yes -- Franta et al. 2015: n,k 0.142–125 µm
- main/Ta2O5/Gao -- Gao et al. 2012: n,k 0.35–1.8 µm
    - `Gao` axis=none (isotropic/cubic/amorphous), range=0.350-1.800 um, covers 633nm: yes -- Gao et al. 2012: n,k 0.35–1.8 µm
- main/Ta2O5/Franta-2025 -- Franta et al. 2025: Polycrystalline
    - `Franta-2025` axis=none (isotropic/cubic/amorphous), range=0.116-400.286 um, covers 633nm: yes -- Franta et al. 2025: Polycrystalline; n,k 0.116–400 µm
- main/Ta2O5/Cheikh-crystalline-3.28-8-650 -- Cheikh et al. 2025: Power 3.28, O2 8, Anneal. 650
    - `Cheikh-crystalline-3.28-8-650` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 3.28, O2 8, Anneal. 650; n,k 0.207–1.24 µm
- main/Ta2O5/Cheikh-crystalline-3.28-8-750 -- Cheikh et al. 2025: Power 3.28, O2 8, Anneal. 750
    - `Cheikh-crystalline-3.28-8-750` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 3.28, O2 8, Anneal. 750; n,k 0.207–1.24 µm
- main/Ta2O5/Cheikh-crystalline-3.28-8-850 -- Cheikh et al. 2025: Power 3.28, O2 8, Anneal. 850
    - `Cheikh-crystalline-3.28-8-850` axis=none (isotropic/cubic/amorphous), range=0.207-1.240 um, covers 633nm: yes -- Cheikh et al. 2025: Power 3.28, O2 8, Anneal. 850; n,k 0.207–1.24 µm
- main/Ta2O5/Bright-nanocrystalline -- Bright et al. 2013: Nanocrystalline film
    - `Bright-nanocrystalline` axis=none (isotropic/cubic/amorphous), range=0.500-1000.000 um, covers 633nm: yes -- Bright et al. 2013: Nanocrystalline film; n,k 0.5–1000 µm


## 40. TGG (Tb3Ga5O12) -- list polymorph: garnet
- **main/Tb3Ga5O12/Schlarb -- Schlarb and Sugg 1994: n 0.405–1.18 µm** (DEFAULT)
    - `Schlarb` axis=none (isotropic/cubic/amorphous), range=0.405-1.177 um, covers 633nm: yes, dataset_label=`garnet | Schlarb1994` -- Schlarb and Sugg 1994: n 0.405–1.18 µm
- main/Tb3Ga5O12/Franta -- Franta et al. 2025: n,k 0.120–400 µm
    - `Franta` axis=none (isotropic/cubic/amorphous), range=0.120-400.009 um, covers 633nm: yes -- Franta et al. 2025: n,k 0.120–400 µm


## 41. Tellurium dioxide (TeO2)
- **main/TeO2/Uchida -- Uchida 1971: α-TeO<sub>2</sub>** (DEFAULT)
    - `Uchida-o` axis=ordinary (o), range=0.400-1.000 um, covers 633nm: yes, dataset_label=`Uchida1971 | o-ray` -- Uchida 1971: α-TeO<sub>2</sub>; n(o) 0.4–1.0 µm
    - `Uchida-e` axis=extraordinary (e), range=0.400-1.000 um, covers 633nm: yes, dataset_label=`Uchida1971 | e-ray` -- Uchida 1971: α-TeO<sub>2</sub>; n(e) 0.4–1.0 µm


## 42. Titanium dioxide (rutile / anatase) (TiO2) -- list polymorph: rutile/anatase
- **main/TiO2/Devore -- Devore 1951:  0.43–1.53 µm** (DEFAULT)
    - `Devore-o` axis=ordinary (o), range=0.430-1.530 um, covers 633nm: yes, dataset_label=`rutile | Devore1951 | o-ray` -- Devore 1951: n(o) 0.43–1.53 µm
    - `Devore-e` axis=extraordinary (e), range=0.430-1.530 um, covers 633nm: yes, dataset_label=`rutile | Devore1951 | e-ray` -- Devore 1951: n(e) 0.43–1.53 µm
- main/TiO2/Bond -- Bond 1965:  0.45–2.4 µm
    - `Bond-o` axis=ordinary (o), range=0.450-2.400 um, covers 633nm: yes -- Bond 1965: n(o) 0.45–2.4 µm
    - `Bond-e` axis=extraordinary (e), range=0.450-2.400 um, covers 633nm: yes -- Bond 1965: n(e) 0.45–2.4 µm
- main/TiO2/Jolivet-anatase -- Jolivet et al. 2023: Anatase thin film
    - `Jolivet-anatase` axis=none (isotropic/cubic/amorphous), range=0.207-0.827 um, covers 633nm: yes -- Jolivet et al. 2023: Anatase thin film; n,k 0.207–0.827 µm
- main/TiO2/Jolivet-amorphous -- Jolivet et al. 2023: Amorphous thin film
    - `Jolivet-amorphous` axis=none (isotropic/cubic/amorphous), range=0.207-0.827 um, covers 633nm: yes -- Jolivet et al. 2023: Amorphous thin film; n,k 0.207–0.827 µm
- main/TiO2/Sarkar -- Sarkar et al. 2019: Thin film
    - `Sarkar` axis=none (isotropic/cubic/amorphous), range=0.300-1.690 um, covers 633nm: yes -- Sarkar et al. 2019: Thin film; n,k 0.30–1.69 µm
- main/TiO2/Siefke -- Siefke et al. 2016: Thin film
    - `Siefke` axis=none (isotropic/cubic/amorphous), range=0.120-125.123 um, covers 633nm: yes -- Siefke et al. 2016: Thin film; n,k 0.120–125 µm
- main/TiO2/Zhukovsky -- Zhukovsky et al. 2015: Thin film
    - `Zhukovsky` axis=none (isotropic/cubic/amorphous), range=0.211-1.690 um, covers 633nm: yes -- Zhukovsky et al. 2015: Thin film; n 0.211–1.69 µm
- main/TiO2/Franta -- Franta et al. 2015: Thin film
    - `Franta` axis=none (isotropic/cubic/amorphous), range=0.114-125.124 um, covers 633nm: yes -- Franta et al. 2015: Thin film; n,k 0.114–125 µm
- main/TiO2/Bodurov -- Bodurov et al. 2016: Nanoparticles
    - `Bodurov` axis=none (isotropic/cubic/amorphous), range=0.405-0.635 um, covers 633nm: yes -- Bodurov et al. 2016: Nanoparticles; n 0.405–0.635 µm
- main/TiO2/Kischkat -- Kischkat et al. 2012: Thin film
    - `Kischkat` axis=none (isotropic/cubic/amorphous), range=1.538-14.286 um, covers 633nm: no -- Kischkat et al. 2012: Thin film; n,k 1.54–14.29 µm


## 43. Barium titanate (BaTiO3)
- **main/BaTiO3/Wemple -- Wemple et al. 1968:  0.4–0.7 µm** (DEFAULT)
    - `Wemple-o` axis=ordinary (o), range=0.400-0.700 um, covers 633nm: yes, dataset_label=`Wemple1968 | o-ray` -- Wemple et al. 1968: n(o) 0.4–0.7 µm
    - `Wemple-e` axis=extraordinary (e), range=0.400-0.700 um, covers 633nm: yes, dataset_label=`Wemple1968 | e-ray` -- Wemple et al. 1968: n(e) 0.4–0.7 µm
- main/BaTiO3/Johnston-x -- Johnston 1971: Unclamped measurements
    - `Johnston-x` axis=none (isotropic/cubic/amorphous), range=0.400-1.000 um, covers 633nm: yes -- Johnston 1971: Unclamped measurements; n 0.4–1.0 µm
- main/BaTiO3/Johnston-x-clamped -- Johnston 1971: Clamped measurements
    - `Johnston-x-clamped` axis=none (isotropic/cubic/amorphous), range=0.400-1.000 um, covers 633nm: yes -- Johnston 1971: Clamped measurements; n,k 0.4–1.0 µm
- main/BaTiO3/Wohlecke-a-300K -- Wöhlecke et al. 1977: Amorphous; 300 K
    - `Wohlecke-a-300K` axis=none (isotropic/cubic/amorphous), range=0.300-1.000 um, covers 633nm: yes -- Wöhlecke et al. 1977: Amorphous; n 0.3–1.0 µm; 300 K
- main/BaTiO3/Wohlecke-a-500K -- Wöhlecke et al. 1977: Amorphous; 500K
    - `Wohlecke-a-500K` axis=none (isotropic/cubic/amorphous), range=0.300-1.000 um, covers 633nm: yes -- Wöhlecke et al. 1977: Amorphous; n 0.3–1.0 µm; 500K
- main/BaTiO3/Wohlecke-mx -- Wöhlecke et al. 1977: Microcrystalline
    - `Wohlecke-mx` axis=none (isotropic/cubic/amorphous), range=0.300-1.000 um, covers 633nm: yes -- Wöhlecke et al. 1977: Microcrystalline; n 0.3–1.0 µm
- main/BaTiO3/Timpu -- Timpu et al. 2019: n 0.4–0.8 µm
    - `Timpu` axis=none (isotropic/cubic/amorphous), range=0.350-0.800 um, covers 633nm: yes -- Timpu et al. 2019: n 0.4–0.8 µm


## 44. Strontium titanate (SrTiO3)
- **main/SrTiO3/Bond -- Bond 1965: n 0.43–3.8 µm** (DEFAULT)
    - `Bond` axis=none (isotropic/cubic/amorphous), range=0.430-3.800 um, covers 633nm: yes, dataset_label=`Bond1965` -- Bond 1965: n 0.43–3.8 µm
- main/SrTiO3/Wohlecke-a -- Wöhlecke et al. 1977: Amorphous
    - `Wohlecke-a` axis=none (isotropic/cubic/amorphous), range=0.300-1.000 um, covers 633nm: yes -- Wöhlecke et al. 1977: Amorphous; n 0.3–1.0 µm
- main/SrTiO3/Wohlecke-mx -- Wöhlecke et al. 1977: Microcrystalline
    - `Wohlecke-mx` axis=none (isotropic/cubic/amorphous), range=0.300-1.000 um, covers 633nm: yes -- Wöhlecke et al. 1977: Microcrystalline; n 0.3–1.0 µm


## 45. Vanadium dioxide (VO2)
- **main/VO2/Beaini-25C -- Beaini et al. 2020: n,k 0.5–25 µm; 25 °C** (DEFAULT)
    - `Beaini-25C` axis=none (isotropic/cubic/amorphous), range=0.500-25.000 um, covers 633nm: yes, dataset_label=`Beaini2020` -- Beaini et al. 2020: n,k 0.5–25 µm; 25 °C
- main/VO2/Beaini-100C -- Beaini et al. 2020: n,k 0.5–25 µm; 100 °C
    - `Beaini-100C` axis=none (isotropic/cubic/amorphous), range=0.500-25.000 um, covers 633nm: yes -- Beaini et al. 2020: n,k 0.5–25 µm; 100 °C
- main/VO2/Oguntoye-20C -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 20 °C
    - `Oguntoye-20C` axis=none (isotropic/cubic/amorphous), range=0.210-2.500 um, covers 633nm: yes -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 20 °C
- main/VO2/Oguntoye-30C -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 30 °C
    - `Oguntoye-30C` axis=none (isotropic/cubic/amorphous), range=0.210-2.500 um, covers 633nm: yes -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 30 °C
- main/VO2/Oguntoye-40C -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 40 °C
    - `Oguntoye-40C` axis=none (isotropic/cubic/amorphous), range=0.210-2.500 um, covers 633nm: yes -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 40 °C
- main/VO2/Oguntoye-50C -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 50 °C
    - `Oguntoye-50C` axis=none (isotropic/cubic/amorphous), range=0.210-2.500 um, covers 633nm: yes -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 50 °C
- main/VO2/Oguntoye-55C -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 55 °C
    - `Oguntoye-55C` axis=none (isotropic/cubic/amorphous), range=0.210-2.500 um, covers 633nm: yes -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 55 °C
- main/VO2/Oguntoye-60C -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 60 °C
    - `Oguntoye-60C` axis=none (isotropic/cubic/amorphous), range=0.210-2.500 um, covers 633nm: yes -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 60 °C
- main/VO2/Oguntoye-70C -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 70 °C
    - `Oguntoye-70C` axis=none (isotropic/cubic/amorphous), range=0.210-2.500 um, covers 633nm: yes -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 70 °C
- main/VO2/Oguntoye-80C -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 80 °C
    - `Oguntoye-80C` axis=none (isotropic/cubic/amorphous), range=0.210-2.500 um, covers 633nm: yes -- Oguntoye et al. 2023: n,k 0.21–2.5 µm; 80 °C


## 46. Yttrium orthovanadate (YVO4)
- **main/YVO4/Birnbaum -- Birnbaum and DeShazer 1976:  0.488–3.39 µm** (DEFAULT)
    - `Birnbaum-o` axis=ordinary (o), range=0.488-3.390 um, covers 633nm: yes, dataset_label=`Birnbaum1976 | o-ray` -- Birnbaum and DeShazer 1976: n(o) 0.488–3.39 µm
    - `Birnbaum-e` axis=extraordinary (e), range=0.488-3.390 um, covers 633nm: yes, dataset_label=`Birnbaum1976 | e-ray` -- Birnbaum and DeShazer 1976: n(e) 0.488–3.39 µm
- main/YVO4/Shi -- Shi et al. 2001:  0.48–1.34 µm; 20 °C
    - `Shi-o-20C` axis=ordinary (o), range=0.480-1.340 um, covers 633nm: yes -- Shi et al. 2001: n(o) 0.48–1.34 µm; 20 °C
    - `Shi-e-20C` axis=extraordinary (e), range=0.480-1.340 um, covers 633nm: yes -- Shi et al. 2001: n(e) 0.48–1.34 µm; 20 °C
- main/YVO4/Shi -- Shi et al. 2001:  0.48–1.34 µm; 50 °C
    - `Shi-o-50C` axis=ordinary (o), range=0.480-1.340 um, covers 633nm: yes -- Shi et al. 2001: n(o) 0.48–1.34 µm; 50 °C
    - `Shi-e-50C` axis=extraordinary (e), range=0.480-1.340 um, covers 633nm: yes -- Shi et al. 2001: n(e) 0.48–1.34 µm; 50 °C
- main/YVO4/Shi -- Shi et al. 2001:  0.48–1.34 µm; 80 °C
    - `Shi-o-80C` axis=ordinary (o), range=0.480-1.340 um, covers 633nm: yes -- Shi et al. 2001: n(o) 0.48–1.34 µm; 80 °C
    - `Shi-e-80C` axis=extraordinary (e), range=0.480-1.340 um, covers 633nm: yes -- Shi et al. 2001: n(e) 0.48–1.34 µm; 80 °C
- main/YVO4/Shi -- Shi et al. 2001:  0.48–1.34 µm; 110 °C
    - `Shi-o-110C` axis=ordinary (o), range=0.480-1.340 um, covers 633nm: yes -- Shi et al. 2001: n(o) 0.48–1.34 µm; 110 °C
    - `Shi-e-110C` axis=extraordinary (e), range=0.480-1.340 um, covers 633nm: yes -- Shi et al. 2001: n(e) 0.48–1.34 µm; 110 °C
- main/YVO4/Shi -- Shi et al. 2001:  0.48–1.34 µm; 140 °C
    - `Shi-o-140C` axis=ordinary (o), range=0.480-1.340 um, covers 633nm: yes -- Shi et al. 2001: n(o) 0.48–1.34 µm; 140 °C
    - `Shi-e-140C` axis=extraordinary (e), range=0.480-1.340 um, covers 633nm: yes -- Shi et al. 2001: n(e) 0.48–1.34 µm; 140 °C


## 47. Tungsten trioxide (WO3)
- **main/WO3/Kulikova -- Kulikova et al. 2020: n,k 0.3–1.0 µm** (DEFAULT)
    - `Kulikova` axis=none (isotropic/cubic/amorphous), range=0.300-1.000 um, covers 633nm: yes, dataset_label=`Kulikova2020` -- Kulikova et al. 2020: n,k 0.3–1.0 µm


## 48. Yttrium oxide (Y2O3)
- **main/Y2O3/Nigara -- Nigara 1968: n 0.25–9.6 µm** (DEFAULT)
    - `Nigara` axis=none (isotropic/cubic/amorphous), range=0.250-9.600 um, covers 633nm: yes, dataset_label=`Nigara1968` -- Nigara 1968: n 0.25–9.6 µm


## 49. YAG (Y3Al5O12) -- list polymorph: garnet
- **main/Y3Al5O12/Zelmon -- Zelmon et al. 1998: n 0.4–5.0 µm** (DEFAULT)
    - `Zelmon` axis=none (isotropic/cubic/amorphous), range=0.400-5.000 um, covers 633nm: yes, dataset_label=`garnet | Zelmon1998` -- Zelmon et al. 1998: n 0.4–5.0 µm
- main/Y3Al5O12/Hrabovsky -- Hrabovský et al. 2021: n 0.193–1.69 µm
    - `Hrabovsky` axis=none (isotropic/cubic/amorphous), range=0.193-1.690 um, covers 633nm: yes -- Hrabovský et al. 2021: n 0.193–1.69 µm
- main/Y3Al5O12/Franta -- Franta et al. 2021: n,k 0.120–400 µm
    - `Franta` axis=none (isotropic/cubic/amorphous), range=0.120-400.286 um, covers 633nm: yes -- Franta et al. 2021: n,k 0.120–400 µm
- main/Y3Al5O12/Bond -- Bond 1965: n 0.4–4.0 µm
    - `Bond` axis=none (isotropic/cubic/amorphous), range=0.400-4.000 um, covers 633nm: yes -- Bond 1965: n 0.4–4.0 µm


## 50. Zinc oxide (ZnO)
- **main/ZnO/Bond -- Bond et al. 1965:  0.45–4.0 µm** (DEFAULT)
    - `Bond-o` axis=ordinary (o), range=0.450-4.000 um, covers 633nm: yes, dataset_label=`Bond1965 | o-ray` -- Bond et al. 1965: n(o) 0.45–4.0 µm
    - `Bond-e` axis=extraordinary (e), range=0.450-4.000 um, covers 633nm: yes, dataset_label=`Bond1965 | e-ray` -- Bond et al. 1965: n(e) 0.45–4.0 µm
- main/ZnO/Stelling -- Stelling et al. 2017: n,k 0.302–1.685 µm
    - `Stelling` axis=none (isotropic/cubic/amorphous), range=0.302-1.685 um, covers 633nm: yes -- Stelling et al. 2017: n,k 0.302–1.685 µm
- main/ZnO/Aguilar -- Aguilar et al. 2019: n,k 0.3–3.2 µm
    - `Aguilar` axis=none (isotropic/cubic/amorphous), range=0.300-3.200 um, covers 633nm: yes -- Aguilar et al. 2019: n,k 0.3–3.2 µm
- main/ZnO/Querry -- Querry 1985: n,k 0.21–55.6 µm
    - `Querry` axis=none (isotropic/cubic/amorphous), range=0.210-55.556 um, covers 633nm: yes -- Querry 1985: n,k 0.21–55.6 µm
- main/ZnO/Bodurov -- Bodurov et al. 2016: Nanoparticles
    - `Bodurov` axis=none (isotropic/cubic/amorphous), range=0.405-0.635 um, covers 633nm: yes -- Bodurov et al. 2016: Nanoparticles; n 0.405–0.635 µm
