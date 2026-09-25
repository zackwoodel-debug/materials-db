#!/usr/bin/env python3
"""
scripts/release_dielectric.py
=============================
Release build stage 4b: Materials Project DFPT dielectric constants (data/descriptors/mp_dielectric.json, cached by
scripts/fetch_mp_dielectric.py) as physical_properties rows. Runs after the descriptors, whose structural block says which MP
entry each material uses and whether that entry IS the material.

Per material with MP dielectric data, two rows (dielectric_constant), labelled with the phase prefix of the material's density
row when it has one:
  "<phase> | dielectric_static_total | MP_DFPT"   static (electronic + ionic) epsilon, frequency_hz = 0
  "<phase> | dielectric_electronic | MP_DFPT"     clamped-ion (optical, epsilon_inf) epsilon, frequency_hz NULL
Each value is the mean of the tensor's principal values (the full tensors stay in the cache). Calculated at 0 K, not measured.

Not stored (each listed in the manifest with the reason):
  * the MP entry is only a crystalline REFERENCE for the sample (an amorphous or film sample, or a density taken from elsewhere):
    a crystal's DFT dielectric constant does not describe a glass or a film;
  * MP's own (PBE) band gap is below MIN_GAP_EV: DFPT on a (nearly) gapless PBE state overestimates epsilon badly. Against
    measured static epsilon: gap 0 eV Ge/GaSb/InSb +46..+62%, 0.18-0.47 eV GaAs/InP +32..+38%, >= 0.5 eV at most +26% (CdTe),
    typically 0..+18% (tests/test_release_dielectric.py keeps this benchmark).
"""
import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
CACHE = _ROOT / "data" / "descriptors" / "mp_dielectric.json"
SOURCE = dict(
    doi="10.1038/sdata.2016.134",
    title="High-throughput screening of inorganic compounds for the discovery of novel dielectric and optical materials",
    authors="I. Petousis, D. Mrdjenovich, E. Ballouz, M. Liu, D. Winston, W. Chen, T. Graf, T. D. Schladt, K. A. Persson, F. B. Prinz",
    journal="Scientific Data", year=2017, technique="DFT (density functional perturbation theory), Materials Project",
    url="https://materialsproject.org")
THE_MATERIAL = "the material"
MIN_GAP_EV = 0.5


def _phase_prefix(conn, mid):
    row = conn.execute("SELECT dataset_label FROM physical_properties WHERE material_id = ? AND density_g_cm3 IS NOT NULL", (mid,)).fetchone()
    if not row or " | density_" not in (row[0] or ""):
        return None
    return row[0].split(" | density_")[0]


def populate(conn, cache_path=CACHE):
    cache = json.loads(Path(cache_path).read_text())
    entries = cache["entries"]
    conn.execute("INSERT INTO sources(doi, title, authors, journal, year, technique, url, notes) VALUES (?,?,?,?,?,?,?,?)",
                 (SOURCE["doi"], SOURCE["title"], SOURCE["authors"], SOURCE["journal"], SOURCE["year"], SOURCE["technique"], SOURCE["url"],
                  f"Materials Project database {cache['mp_database_version']}, dielectric (DFPT) task per material; CC BY 4.0. "
                  "Calculated, not measured; epsilon = mean of the tensor's principal values. See data/descriptors/mp_dielectric.json."))
    sid = conn.execute("SELECT source_id FROM sources WHERE doi = ?", (SOURCE["doi"],)).fetchone()[0]
    stored, reference_only, narrow_gap = [], [], []
    for mid, name, doc in conn.execute("SELECT m.material_id, m.name, d.descriptor_json FROM materials m "
                                       "JOIN chemical_descriptors d USING(material_id) ORDER BY m.material_id").fetchall():
        struct = json.loads(doc)["structural"]
        mp_id = struct.get("mp_id")
        if mp_id not in entries:
            continue
        if not str(struct.get("applies_to", "")).startswith(THE_MATERIAL):
            reference_only.append(dict(material=name, mp_id=mp_id, applies_to=struct.get("applies_to")))
            continue
        gap = struct.get("band_gap_ev")
        if gap is None or gap < MIN_GAP_EV:
            narrow_gap.append(dict(material=name, mp_id=mp_id, mp_band_gap_ev=gap))
            continue
        e = entries[mp_id]
        prefix = _phase_prefix(conn, mid)
        label = lambda kind: " | ".join(x for x in (prefix, kind, "MP_DFPT") if x)
        conn.execute("INSERT INTO physical_properties(material_id, dielectric_constant, frequency_hz, dataset_label, source_id) "
                     "VALUES (?,?,?,?,?)", (mid, e["e_total"], 0.0, label("dielectric_static_total"), sid))
        conn.execute("INSERT INTO physical_properties(material_id, dielectric_constant, frequency_hz, dataset_label, source_id) "
                     "VALUES (?,?,?,?,?)", (mid, e["e_electronic"], None, label("dielectric_electronic"), sid))
        stored.append(name)
    return dict(materials=len(stored), rows=2 * len(stored), mp_database_version=cache["mp_database_version"],
                not_stored_reference_only=reference_only, not_stored_narrow_gap=narrow_gap, min_gap_ev=MIN_GAP_EV)
