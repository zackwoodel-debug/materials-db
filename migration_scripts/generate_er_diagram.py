#!/usr/bin/env python3
"""Generate a compact ER diagram for the normalized schema."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib"))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


OUTPUT = ROOT / "ER_diagram.png"

TABLES = {
    "materials": ["material_id PK", "name", "formula", "smiles", "inchikey"],
    "material_synonyms": ["synonym_id PK", "material_id FK", "synonym"],
    "sources": ["source_id PK", "doi", "title", "technique", "uncertainty"],
    "chemical_descriptors": ["material_id PK/FK", "descriptor_json", "morgan_fp"],
    "optical_dispersion": ["record_id PK", "material_id FK", "wavelength_nm", "n", "k", "source_id FK"],
    "mechanical_properties": ["record_id PK", "material_id FK", "temperature_c", "frequency_hz", "source_id FK"],
    "rheology": ["record_id PK", "material_id FK", "viscosity_pas", "shear_rate_s_inv", "source_id FK"],
    "physical_properties": ["record_id PK", "material_id FK", "density_g_cm3", "xray_sld", "source_id FK"],
    "consensus_properties": ["material_id FK", "property_name", "consensus_value", "confidence_score"],
    "dataset_validation": ["validation_id PK", "material_id FK", "property_name", "pearson_r", "rmse"],
}

POSITIONS = {
    "materials": (0.43, 0.75),
    "sources": (0.75, 0.75),
    "material_synonyms": (0.12, 0.75),
    "chemical_descriptors": (0.12, 0.47),
    "optical_dispersion": (0.43, 0.47),
    "mechanical_properties": (0.75, 0.47),
    "rheology": (0.12, 0.18),
    "physical_properties": (0.43, 0.18),
    "consensus_properties": (0.75, 0.18),
    "dataset_validation": (0.43, 0.02),
}

EDGES = [
    ("material_synonyms", "materials"),
    ("chemical_descriptors", "materials"),
    ("optical_dispersion", "materials"),
    ("mechanical_properties", "materials"),
    ("rheology", "materials"),
    ("physical_properties", "materials"),
    ("consensus_properties", "materials"),
    ("dataset_validation", "materials"),
    ("optical_dispersion", "sources"),
    ("mechanical_properties", "sources"),
    ("rheology", "sources"),
    ("physical_properties", "sources"),
]


def draw_box(ax, name: str, fields: list[str], x: float, y: float) -> None:
    width = 0.23
    height = 0.15
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.01",
        linewidth=1.1,
        edgecolor="#334155",
        facecolor="#f8fafc",
    )
    ax.add_patch(box)
    ax.text(x + 0.012, y + height - 0.026, name, fontsize=10, weight="bold", color="#0f172a")
    for index, field in enumerate(fields[:5]):
        ax.text(x + 0.012, y + height - 0.052 - index * 0.018, field, fontsize=7.4, color="#334155")


def main() -> None:
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("Normalized Materials Informatics ER Diagram", fontsize=18, weight="bold")

    for name, fields in TABLES.items():
        draw_box(ax, name, fields, *POSITIONS[name])

    for child, parent in EDGES:
        child_x, child_y = POSITIONS[child]
        parent_x, parent_y = POSITIONS[parent]
        ax.annotate(
            "",
            xy=(parent_x + 0.115, parent_y + 0.075),
            xytext=(child_x + 0.115, child_y + 0.075),
            arrowprops={"arrowstyle": "->", "color": "#64748b", "lw": 0.9},
        )

    fig.tight_layout()
    fig.savefig(OUTPUT, dpi=220, bbox_inches="tight")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
