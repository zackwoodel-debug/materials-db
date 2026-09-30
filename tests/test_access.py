"""materials_db.access: read-only library, HTTP API and MCP server over the release. Needs a built release (skipped otherwise);
the MCP test needs the `mcp` SDK (skipped otherwise)."""
import asyncio
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db.access import AccessError, ReleaseDB, find_release  # noqa: E402

try:
    find_release()
    HAVE_RELEASE = True
except AccessError:
    HAVE_RELEASE = False
pytestmark = pytest.mark.skipif(not HAVE_RELEASE, reason="no release built locally")


@pytest.fixture(scope="module")
def db():
    return ReleaseDB()


def test_primary_matches_the_ml_set(db):
    spec = pd.read_parquet(ROOT / "data" / "ML_release_spectra.parquet", columns=["material_id", "source_file", "is_primary"])
    meta = json.loads((ROOT / "data" / "ML_release_spectra_metadata.json").read_text())
    if meta["source_release"] != db.version:
        pytest.skip("ML set is from another release")
    prim = spec[spec.is_primary].set_index("material_id").source_file.to_dict()
    assert db.primary_unavailable is None and len(db.primary) == len(db.materials)
    assert {k: v for k, v in db.primary.items() if k in prim} == prim


def test_nk_at_matches_the_ml_feature_matrix(db):
    fm = pd.read_parquet(ROOT / "data" / "ML_release_feature_matrix.parquet", columns=["material_id", "target_n_633nm", "target_k_633nm"])
    checked = 0
    for r in fm.dropna(subset=["target_n_633nm"]).sample(60, random_state=0).itertuples():
        got = db.nk_at(r.material_id, 633)
        assert got["n"] == pytest.approx(r.target_n_633nm, rel=1e-9)
        if not math.isnan(r.target_k_633nm):
            assert got["k"] == pytest.approx(r.target_k_633nm, rel=1e-9, abs=1e-15)
        checked += 1
    assert checked == 60


def test_nk_never_extrapolates(db):
    d = db.material("GaAs")["optical_datasets"]
    prim = next(x for x in d if x["is_primary"])
    with pytest.raises(AccessError, match="outside"):
        db.nk_at("GaAs", prim["wl_max_nm"] * 1.01)
    edge = db.nk_at("GaAs", prim["wl_min_nm"])
    assert edge["n"] is not None
    every = db.nk_at("GaAs", 10_000, all_datasets=True)["datasets"]
    for x in every:
        assert x["covers"] == (x["wl_range_nm"][0] <= 10_000 <= x["wl_range_nm"][1] and x["n"] is not None) or x["k"] is not None


def test_resolve_by_id_key_name_synonym_formula_and_ambiguity(db):
    gaas = db.resolve("GaAs")
    assert db.resolve(str(gaas)) == db.resolve("semiconductors:GaAs") == db.resolve("gallium arsenide") == gaas
    with pytest.raises(AccessError, match="ambiguous"):
        db.resolve("C")
    with pytest.raises(AccessError, match="candidates"):
        db.resolve("PMMA")


def test_optical_points_are_source_points(db):
    out = db.optical("water", max_points=50)
    assert out["thinned"] and out["returned"] <= 50
    raw = sqlite3.connect(db.sqlite_path).execute(
        "SELECT wavelength_nm, n FROM optical_dispersion WHERE material_id=? AND dataset_label=?",
        (out["material_id"], out["dataset"]["dataset_label"])).fetchall()
    raw = set(raw)
    assert all((p["wavelength_nm"], p["n"]) in raw for p in out["data"])
    ws = [p["wavelength_nm"] for p in out["data"]]
    assert ws == sorted(ws) and ws[0] == min(w for w, _ in raw) and ws[-1] == max(w for w, _ in raw)


def test_material_lists_every_dataset_with_its_source(db):
    m = db.material("GaAs")
    n = sqlite3.connect(db.sqlite_path).execute("SELECT COUNT(DISTINCT dataset_label) FROM optical_dispersion WHERE material_id=?",
                                                (m["material_id"],)).fetchone()[0]
    assert len(m["optical_datasets"]) == n and sum(d["is_primary"] for d in m["optical_datasets"]) == 1
    assert all(d["source"] and d["source"]["title"] for d in m["optical_datasets"])
    json.dumps(m)  # JSON-able, no NaN
    assert "NaN" not in json.dumps(m)


@pytest.mark.parametrize("bad", ["DELETE FROM materials", "select 1; drop table materials", "ATTACH DATABASE 'x.db' AS x",
                                 "WITH x AS (SELECT 1) INSERT INTO sources(title) SELECT 'a'", "PRAGMA writable_schema=1",
                                 "SELECT load_extension('x')", "UPDATE materials SET name='x'"])
def test_sql_refuses_anything_but_reading(db, bad):
    with pytest.raises(AccessError):
        db.sql(bad)
    assert db.con.execute("SELECT COUNT(*) FROM materials").fetchone()[0] == len(db.materials)


def test_sql_reads_and_caps(db):
    r = db.sql("SELECT material_id, name FROM materials ORDER BY material_id", limit=5)
    assert r["columns"] == ["material_id", "name"] and len(r["rows"]) == 5 and r["truncated"]
    r = db.sql("WITH t AS (SELECT COUNT(*) AS c FROM optical_dispersion) SELECT c FROM t")
    assert r["rows"][0][0] > 0 and not r["truncated"]


def test_connection_is_read_only_even_without_the_authorizer(db):
    with pytest.raises(sqlite3.OperationalError):
        db.con.execute("DELETE FROM materials")


def test_http_api(db):
    from fastapi.testclient import TestClient
    from materials_db.access import http
    http.get_db.cache_clear()
    c = TestClient(http.app)
    assert c.get("/info").json()["release"] == db.version
    assert c.get("/materials", params={"q": "sapphire"}).json()["total"] >= 1
    r = c.get("/materials/GaAs/nk", params={"wavelength_nm": 633}).json()
    assert r["n"] == pytest.approx(db.nk_at("GaAs", 633)["n"])
    assert c.get("/materials/nonexistent-zzz").status_code == 404
    assert c.get("/materials/C").status_code == 400
    assert c.post("/sql", json={"query": "DELETE FROM materials"}).status_code == 400
    assert c.post("/sql", json={"query": "SELECT COUNT(*) FROM materials"}).json()["rows"] == [[len(db.materials)]]
    assert c.get("/materials/GaAs/nk", params={"wavelength_nm": -1}).status_code == 422


def test_mcp_server_tools():
    pytest.importorskip("mcp")
    from materials_db.access.mcp_server import build_server
    server = build_server()

    async def run():
        tools = {t.name: t for t in await server.list_tools()}
        assert set(tools) == {"database_info", "search_materials", "get_material", "get_nk_at", "get_optical_data",
                              "compare_datasets", "run_sql"}
        assert all(_read_only_hint(t.annotations) is True for t in tools.values())
    asyncio.run(run())


def _read_only_hint(annotations):
    """The tool's read-only hint under either SDK's field name (mcp 1.x readOnlyHint, 2.x read_only_hint); neither is a failure."""
    for name in ("readOnlyHint", "read_only_hint"):
        if hasattr(annotations, name):
            return getattr(annotations, name)
    raise AssertionError(f"no read-only hint on {annotations!r}")
