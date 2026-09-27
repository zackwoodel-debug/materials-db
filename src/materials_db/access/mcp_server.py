"""MCP server over a materials-db release: lets an AI assistant (Claude Code, Claude Desktop, any MCP client) look up
materials, optical constants, sources and comparisons, and run read-only SQL, with the release's own rules (see db.py).

    pip install mcp                      # the MCP Python SDK, 1.x or 2.x
    PYTHONPATH=src python3 -m materials_db.access.mcp_server [--release PATH]      # stdio transport

Claude Code:   claude mcp add materials-db -e PYTHONPATH="$PWD/src" -- python3 -m materials_db.access.mcp_server
"""
import argparse
import json

import functools

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from .db import AccessError, ReleaseDB

INSTRUCTIONS = """materials-db: measured and modelled optical constants (n, k versus wavelength), densities, scattering length
densities and descriptors of ~380 materials, each value traceable to its source paper.
Workflow: search_materials -> get_material (identity, properties, every optical dataset with its source) -> get_nk_at or
get_optical_data. Rules: n, k are interpolated only inside a dataset's own range (no extrapolation); the default dataset is the
release's primary one; different phases, axes (o/e), temperatures and pressures are different datasets, so compare like with like
(compare_datasets gives the release's own like-for-like comparisons). Say which dataset and source a number comes from, and whether
it is a model fit. For anything else, read the data dictionary (resource materials-db://dictionary) and use run_sql (read-only)."""

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def _explained(fn):
    """AccessError (unknown or ambiguous material, bad argument, refused SQL) reaches the model with its message: the SDK hides
    the text of any other exception."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except AccessError as exc:
            raise ToolError(str(exc)) from None
    return wrapper


def build_server(release=None):
    db = ReleaseDB(release)
    server = _Server(name="materials-db", instructions=INSTRUCTIONS)

    @server.tool(annotations=READ_ONLY)
    @_explained
    def database_info() -> dict:
        """Release version, license, counts per family, and the rules every answer follows."""
        return db.info()

    @server.tool(annotations=READ_ONLY)
    @_explained
    def search_materials(query: str = "", family: str = "", material_class: str = "", limit: int = 25) -> dict:
        """Find materials by part of a name, formula, synonym or stable key (e.g. 'GaAs', 'sapphire', 'PMMA', 'water'), optionally
        filtered by family (see database_info) or material class. Returns material_id, key, name, formula, family, class."""
        return db.search(query or None, family or None, material_class or None, limit)

    @server.tool(annotations=READ_ONLY)
    @_explained
    def get_material(material: str) -> dict:
        """Everything about one material: identifiers, synonyms, family notes and flags (source disagreements, caveats), physical
        properties (density, x-ray/neutron SLD, dielectric constant) with sources, consensus values, and every optical dataset
        (label, range, temperature, model fit or measured, primary or not, source paper and DOI). `material` is a material_id,
        key, exact name, synonym or formula; an ambiguous one returns the candidates."""
        return db.material(material)

    @server.tool(annotations=READ_ONLY)
    @_explained
    def get_nk_at(material: str, wavelength_nm: float, dataset_label: str = "", all_datasets: bool = False) -> dict:
        """n and k at one wavelength (nm), interpolated linearly between the dataset's stored points, never outside its
        range (a formula dataset is stored densely enough that this is within 1e-6 of the formula). Default: the material's primary dataset; or name a dataset_label; or all_datasets=true for every dataset's value
        side by side (with phase/axis/temperature, which must match before values are compared)."""
        return db.nk_at(material, wavelength_nm, dataset_label or None, all_datasets)

    @server.tool(annotations=READ_ONLY)
    @_explained
    def get_optical_data(material: str, dataset_label: str = "", wl_min_nm: float | None = None, wl_max_nm: float | None = None,
                         max_points: int = 500) -> dict:
        """The source points (wavelength_nm, n, k, temperature_c) of one optical dataset, unchanged; default the primary dataset.
        Long datasets are thinned to max_points evenly spaced source points (thinned=true); narrow the range for full resolution."""
        return db.optical(material, dataset_label or None, wl_min_nm, wl_max_nm, max_points)

    @server.tool(annotations=READ_ONLY)
    @_explained
    def compare_datasets(material: str) -> dict:
        """The release's like-for-like comparisons of a material's optical datasets (same phase, axis, temperature): overlap,
        Pearson r, RMSE, mean relative error and a classification (agree / warning / suspicious)."""
        return db.comparisons(material)

    @server.tool(annotations=READ_ONLY)
    @_explained
    def run_sql(query: str, limit: int = 200) -> dict:
        """One read-only SQL SELECT against the release SQLite (tables: materials, optical_dispersion, physical_properties,
        sources, chemical_descriptors, consensus_properties, dataset_validation, material_synonyms, ...; see the data
        dictionary resource). Writes, ATTACH and PRAGMAs are refused. At most 1000 rows."""
        return db.sql(query, limit)

    @server.resource("materials-db://dictionary", name="data_dictionary", mime_type="application/json",
                     description="Every table and column of the release: type, unit, meaning, label grammar, vocabularies.")
    def dictionary() -> str:
        return json.dumps(db.schema(), indent=1)

    @server.resource("materials-db://datacard", name="data_card", mime_type="text/markdown",
                     description="The release's data card: contents, provenance, rules, caveats, citation.")
    def datacard() -> str:
        p = db.release_dir / "README.md"
        return p.read_text() if p.exists() else "no data card in this release folder"

    return server


def main(argv=None):
    ap = argparse.ArgumentParser(description="materials-db MCP server (stdio)")
    ap.add_argument("--release", default=None, help="release folder or .sqlite (default: $MATERIALS_DB_RELEASE or the newest release/)")
    a = ap.parse_args(argv)
    build_server(a.release).run()


if __name__ == "__main__":
    main()
