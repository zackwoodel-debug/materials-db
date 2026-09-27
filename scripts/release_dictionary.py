#!/usr/bin/env python3
"""
scripts/release_dictionary.py
=============================
The release's data dictionary, for people and for machines (data loaders, AI agents): data_dictionary.json and
DATA_DICTIONARY.md in every release package.

It is built from the release database itself (every table and column, including generated ones, with type, key and reference)
plus the curated descriptions below; the controlled vocabularies (label grammar, quantities, variants, classifications, kinds,
families, the descriptor_json layout) are read from the data. A table or column without a description, or a description of
a column that does not exist, stops the build, so the dictionary cannot drift from the schema.
"""
import json
import re
from collections import Counter
from pathlib import Path

TABLES = {
    "materials": ("One row per material. material_id is permanent across releases (material_registry.csv gives each id its stable "
                  "text key).", {
        "material_id": ("Permanent material id (never reused).", None),
        "name": ("Display name; unique. May be edited between releases: use material_id or the stable key to join.", None),
        "formula": ("Chemical formula as the source states it; NULL for products and mixtures (glasses, polymers of unstated "
                    "composition, formulations, air, biological media).", None),
        "smiles": ("PubChem isomeric SMILES of the substance, where PubChem has it.", None),
        "inchikey": ("PubChem InChIKey.", None),
        "molecular_weight": ("PubChem molecular weight.", "g/mol"),
        "cas_number": ("CAS registry number from PubChem.", None),
        "pubchem_cid": ("PubChem compound id.", None)}),
    "optical_dispersion": ("Refractive index n and extinction coefficient k against wavelength; one row per data point. A DATASET "
                           "is (material_id, dataset_label): one source, one sample variant or phase, one optical axis, one "
                           "temperature.", {
        "record_id": ("Row id (not stable across releases).", None),
        "material_id": ("-> materials.material_id.", None),
        "wavelength_nm": ("Vacuum wavelength.", "nm"),
        "n": ("Real refractive index.", None),
        "k": ("Extinction coefficient (imaginary index); NULL when the source gives none (not 0).", None),
        "eps_real": ("Generated: n^2 - k^2 (NULL unless both n and k are given).", None),
        "eps_imag": ("Generated: 2 n k (NULL unless both n and k are given).", None),
        "temperature_c": ("Sample temperature the source states; NULL when it states none.", "degC"),
        "dataset_label": ("'[variant or phase |] source tag [| axis]', see label_grammar.", None),
        "raw_record_table": ("refractiveindex.info data file the row came from (path under database/data).", None),
        "raw_record_id": ("Row index within that file as parsed (formula pages: the sample index).", None),
        "source_id": ("-> sources.source_id.", None)}),
    "physical_properties": ("Scalar physical properties; the quantity is named in dataset_label (see physical_quantities).", {
        "record_id": ("Row id (not stable across releases).", None),
        "material_id": ("-> materials.material_id.", None),
        "density_g_cm3": ("Density.", "g/cm^3"),
        "xray_sld": ("X-ray scattering length density at Cu K-alpha (8048 eV); real and imaginary parts are separate rows "
                     "(xray_sld_real / xray_sld_imag).", "1e-6 / Angstrom^2"),
        "neutron_sld": ("Thermal-neutron scattering length density; real and imaginary parts are separate rows.", "1e-6 / Angstrom^2"),
        "dielectric_constant": ("Relative permittivity: dielectric_static_total (frequency_hz = 0) or dielectric_electronic "
                                "(epsilon_inf, frequency_hz NULL); Materials Project DFPT, calculated.", None),
        "temperature_c": ("Temperature the value refers to (liquid densities); NULL otherwise.", "degC"),
        "frequency_hz": ("Frequency of a dielectric value (0 = static).", "Hz"),
        "wavelength_nm": ("Radiation wavelength of an SLD row (0.15406 x-ray Cu K-alpha, 0.1798 thermal neutrons).", "nm"),
        "energy_ev": ("Photon energy of an x-ray SLD row.", "eV"),
        "dataset_label": ("'[phase |] quantity[_origin] [| method]', see physical_quantities.", None),
        "raw_record_table": ("Origin table where the value was migrated from a legacy table; NULL otherwise.", None),
        "raw_record_id": ("Row id in raw_record_table.", None),
        "source_id": ("-> sources.source_id.", None)}),
    "sources": ("Every citation: papers (with DOI where one exists), datasheets, databases (Materials Project, PubChem) and "
                "calculation tools (periodictable).", {
        "source_id": ("Source id.", None),
        "doi": ("DOI, lower-case; unique.", None),
        "title": ("Title.", None),
        "authors": ("Authors, or the full citation string when the source gives no separate title.", None),
        "journal": ("Journal.", None),
        "year": ("Year.", None),
        "technique": ("How the values were obtained (e.g. refractiveindex.info, DFT (Materials Project), literature).", None),
        "url": ("URL.", None),
        "uncertainty": ("Reserved; empty in every release (sources rarely state one uniformly).", None),
        "notes": ("What the source is cited for.", None)}),
    "chemical_descriptors": ("One row per material; compositional / structural / molecular descriptors. Columns hold the common "
                             "molecular ones; everything else is in descriptor_json (see descriptor_json_layout).", {
        "material_id": ("-> materials.material_id.", None),
        "exact_mass": ("Monoisotopic mass of the formula unit (repeat unit for polymers).", "u"),
        "tpsa": ("Topological polar surface area (RDKit), molecules and polymer repeat units only.", "Angstrom^2"),
        "logp": ("Wildman-Crippen logP (RDKit), molecules and polymer repeat units only.", None),
        "heavy_atom_count": ("Non-hydrogen atoms per formula unit.", None),
        "rotatable_bonds": ("RDKit rotatable bonds (molecules / repeat units).", None),
        "hbond_donors": ("RDKit H-bond donors (molecules / repeat units).", None),
        "hbond_acceptors": ("RDKit H-bond acceptors (molecules / repeat units).", None),
        "aromatic_rings": ("RDKit aromatic rings (molecules / repeat units).", None),
        "descriptor_json": ("JSON: compositional, structural (Materials Project), molecular blocks, material_kind, family, "
                            "material_class; every NULL column's reason in null_columns_reason.", None),
        "morgan_fp": ("Morgan fingerprint, radius 2, 2048 bits as a 0/1 string (molecules / repeat units).", None)}),
    "dataset_validation": ("Like-for-like comparison of two datasets of one material (same variant/phase, axis and temperature) "
                           "over the wavelengths both cover.", {
        "validation_id": ("Row id.", None),
        "material_id": ("-> materials.material_id.", None),
        "property_name": ("'n' or 'k'.", None),
        "dataset_a": ("dataset_label of the first dataset.", None),
        "dataset_b": ("dataset_label of the second dataset.", None),
        "pearson_r": ("Pearson correlation over the overlap (NULL if either is constant).", None),
        "rmse": ("Root-mean-square difference over the overlap.", None),
        "mean_relative_error": ("n: mean |a-b| / mean(a,b); k: scaled to the largest k, or absolute where k < 0.01.", None),
        "classification": ("excellent (< 2%) / warning (< 10%) / suspicious (>= 10%).", None),
        "notes": ("Overlap range, point count, measured vs model fit, temperature.", None)}),
    "consensus_properties": ("n and k at 633 nm per material, variant/phase and axis, from MEASURED ambient datasets only.", {
        "material_id": ("-> materials.material_id.", None),
        "property_name": ("'n_633nm' or 'k_633nm', with ' | variant' and ' | axis' where they apply.", None),
        "consensus_value": ("Median of the voting datasets.", None),
        "std_dev": ("Sample standard deviation (0 for one source).", None),
        "num_sources": ("Datasets that voted.", None),
        "confidence_score": ("(1 - 0.5^num_sources) * (1 - spread / 10%); one source 0.5.", None),
        "classification": ("single_source / excellent / warning / suspicious on the spread (max - min) / median.", None)}),
    "material_synonyms": ("Other names of a material (alternate names, abbreviations, PubChem titles, spellings); a name that "
                          "would point to two materials is left out.", {
        "synonym_id": ("Row id.", None),
        "material_id": ("-> materials.material_id.", None),
        "synonym": ("The other name.", None)}),
    "mechanical_properties": ("Viscoelastic moduli; reserved, empty in every release.", {
        "record_id": ("Row id.", None), "material_id": ("-> materials.material_id.", None),
        "storage_modulus": ("Storage modulus.", "Pa"), "loss_modulus": ("Loss modulus.", "Pa"),
        "temperature_c": ("Temperature.", "degC"), "frequency_hz": ("Frequency.", "Hz"), "dataset_label": ("Label.", None),
        "raw_record_table": ("Origin table.", None), "raw_record_id": ("Origin row.", None), "source_id": ("-> sources.source_id.", None)}),
    "rheology": ("Viscosity; reserved, empty in every release.", {
        "record_id": ("Row id.", None), "material_id": ("-> materials.material_id.", None),
        "viscosity_pas": ("Viscosity.", "Pa s"), "shear_rate_s_inv": ("Shear rate.", "1/s"),
        "temperature_c": ("Temperature.", "degC"), "context_flag": ("Context.", None), "dataset_label": ("Label.", None),
        "raw_record_table": ("Origin table.", None), "raw_record_id": ("Origin row.", None), "source_id": ("-> sources.source_id.", None)}),
}

LABEL_GRAMMAR = {
    "optical_dispersion.dataset_label": ("'[variant or phase |] source tag [| axis]'. source tag = first author + year (Aspnes1983), "
                                         "a series suffix where one paper has several pages (Wu1993-25.1C, Peck1964-15C), or a "
                                         "manufacturer datasheet (SCHOTT2017). axis: o-ray, e-ray, a/b/c-axis, alpha/beta/gamma-axis "
                                         "(absent = isotropic). variant / phase: a crystal phase, a sample variant (e.g. '10x PBS'), "
                                         "or for gases the state and pressure ('gas, 101.325 kPa', 'liquid', 'solid')."),
    "physical_properties.dataset_label": "'[phase |] quantity[_origin] [| method]', e.g. 'rock salt | density_MP_DFT', "
                                         "'xray_sld_real | periodictable_CuKalpha', 'dielectric_static_total | MP_DFPT'.",
    "comparability": "Two optical datasets are the same physical quantity only with equal variant/phase, equal axis and equal "
                     "temperature; the validation and consensus tables never mix others.",
}


class DictionaryError(RuntimeError):
    pass


def _schema(conn):
    out = {}
    for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        fks = {r[3]: f"{r[2]}.{r[4]}" for r in conn.execute(f"PRAGMA foreign_key_list({t})")}
        out[t] = [dict(name=r[1], type=r[2], not_null=bool(r[3]), primary_key=bool(r[5]), generated=r[6] in (2, 3),
                       references=fks.get(r[1])) for r in conn.execute(f"PRAGMA table_xinfo({t})")]
    return out


def _vocab(conn):
    def distinct(sql):
        return sorted({r[0] for r in conn.execute(sql) if r[0] is not None})
    labels = distinct("SELECT DISTINCT dataset_label FROM optical_dispersion")
    axes = Counter(l.split(" | ")[-1] for l in labels if len(l.split(" | ")) > 1 and l.split(" | ")[-1].endswith(("-ray", "-axis")))
    variants = Counter(l.split(" | ")[0] for l in labels if len(l.split(" | ")) > 1 and not re.search(r"\d{4}", l.split(" | ")[0]))
    quantities = Counter()
    for (lab,) in conn.execute("SELECT dataset_label FROM physical_properties"):
        segs = (lab or "").split(" | ")
        q = next((s for s in segs if re.match(r"(density|xray_sld|neutron_sld|dielectric)", s)), None)
        if q:
            quantities[q] += 1
    docs = [json.loads(d) for (d,) in conn.execute("SELECT descriptor_json FROM chemical_descriptors")]
    layout = {}
    for block in ("compositional", "structural", "molecular"):
        keys = Counter(k for d in docs for k in (d.get(block) or {}))
        layout[block] = sorted(keys)
    return dict(
        optical_axes=dict(sorted(axes.items())),
        optical_variants_and_phases=dict(sorted(variants.items())),
        physical_quantities=dict(sorted(quantities.items())),
        consensus_property_names=distinct("SELECT DISTINCT property_name FROM consensus_properties WHERE property_name NOT LIKE '%|%'"),
        validation_classifications=distinct("SELECT DISTINCT classification FROM dataset_validation"),
        consensus_classifications=distinct("SELECT DISTINCT classification FROM consensus_properties"),
        material_kinds=dict(sorted(Counter(d.get("material_kind") for d in docs).items())),
        families=dict(sorted(Counter(d.get("family") for d in docs).items())),
        material_classes=dict(sorted(Counter(d.get("material_class") for d in docs if d.get("material_class")).items())),
        descriptor_json_layout=dict(top_level=sorted({k for d in docs for k in d}), **layout),
    )


def build(conn, version):
    schema = _schema(conn)
    missing, stale = [], []
    for t, cols in schema.items():
        if t not in TABLES:
            missing.append(t)
            continue
        described = TABLES[t][1]
        missing += [f"{t}.{c['name']}" for c in cols if c["name"] not in described]
        stale += [f"{t}.{c}" for c in described if c not in {x['name'] for x in cols}]
    stale += [t for t in TABLES if t not in schema]
    if missing or stale:
        raise DictionaryError(f"data dictionary out of step with the schema: undescribed {missing}; described but absent {stale}")
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in schema}
    tables = {}
    for t, cols in schema.items():
        desc, coldesc = TABLES[t]
        tables[t] = dict(description=desc, rows=counts[t], columns=[
            dict(c, description=coldesc[c["name"]][0], unit=coldesc[c["name"]][1]) for c in cols])
    return dict(dataset="materials-db", version=version, license="CC-BY-4.0",
                identifiers="materials.material_id is permanent across releases; material_registry.csv maps it to a stable key",
                label_grammar=LABEL_GRAMMAR, tables=tables, vocabularies=_vocab(conn))


def markdown(d):
    lines = [f"# materials-db v{d['version']} data dictionary", "",
             "Machine-readable twin: `data_dictionary.json`. " + d["identifiers"] + ".", "", "## Label grammar", ""]
    lines += [f"- **{k}**: {v}" for k, v in d["label_grammar"].items()]
    for t, spec in d["tables"].items():
        lines += ["", f"## `{t}` ({spec['rows']:,} rows)", "", spec["description"], "", "| column | type | unit | description |",
                  "|---|---|---|---|"]
        for c in spec["columns"]:
            flags = " ".join(x for x, on in (("PK", c["primary_key"]), ("NOT NULL", c["not_null"]), ("generated", c["generated"])) if on)
            ref = f" -> `{c['references']}`" if c["references"] else ""
            lines.append(f"| `{c['name']}` | {c['type'] or ''} {flags}{ref} | {c['unit'] or ''} | {c['description']} |")
    v = d["vocabularies"]
    lines += ["", "## Vocabularies (from the data)", ""]
    for k in ("optical_axes", "physical_quantities", "material_kinds", "families", "material_classes"):
        lines.append(f"- **{k}**: " + ", ".join(f"`{a}` ({b})" for a, b in v[k].items()))
    for k in ("consensus_property_names", "validation_classifications", "consensus_classifications"):
        lines.append(f"- **{k}**: " + ", ".join(f"`{a}`" for a in v[k]))
    lines.append(f"- **optical variants and phases**: {len(v['optical_variants_and_phases'])} distinct; see the JSON")
    lay = v["descriptor_json_layout"]
    lines += ["", "## `descriptor_json` layout", ""] + [f"- **{k}**: " + ", ".join(f"`{x}`" for x in lay[k]) for k in lay]
    return "\n".join(lines) + "\n"


def write(conn, out_dir, version):
    d = build(conn, version)
    Path(out_dir, "data_dictionary.json").write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    Path(out_dir, "DATA_DICTIONARY.md").write_text(markdown(d))
    return dict(tables=len(d["tables"]), columns=sum(len(t["columns"]) for t in d["tables"].values()))
