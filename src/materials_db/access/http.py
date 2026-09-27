"""HTTP API over a materials-db release (read-only), the same queries as the MCP server; OpenAPI docs at /docs.

    PYTHONPATH=src uvicorn materials_db.access.http:app --port 8000      # MATERIALS_DB_RELEASE selects the release
"""
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .db import AccessError, ReleaseDB

app = FastAPI(title="materials-db", description="Read-only access to a materials-db release: materials, optical constants "
              "n(λ), k(λ) with sources, properties, comparisons and SQL. Values are the release's own; n, k are interpolated only "
              "inside a dataset's range.")


@lru_cache(maxsize=1)
def get_db():
    return ReleaseDB()


def _run(fn, *args):
    try:
        return fn(*args)
    except AccessError as exc:
        status = 404 if str(exc).startswith("no material") else 400
        raise HTTPException(status_code=status, detail=str(exc)) from None


@app.get("/info")
def info():
    return get_db().info()


@app.get("/materials")
def search(q: Optional[str] = None, family: Optional[str] = None, material_class: Optional[str] = None,
           limit: int = Query(25, ge=1, le=200)):
    return _run(get_db().search, q, family, material_class, limit)


@app.get("/materials/{material}")
def material(material: str):
    return _run(get_db().material, material)


@app.get("/materials/{material}/nk")
def nk(material: str, wavelength_nm: float = Query(..., gt=0), dataset_label: Optional[str] = None, all_datasets: bool = False):
    return _run(get_db().nk_at, material, wavelength_nm, dataset_label, all_datasets)


@app.get("/materials/{material}/optical")
def optical(material: str, dataset_label: Optional[str] = None, wl_min_nm: Optional[float] = None, wl_max_nm: Optional[float] = None,
            max_points: int = Query(500, ge=2, le=2000)):
    return _run(get_db().optical, material, dataset_label, wl_min_nm, wl_max_nm, max_points)


@app.get("/materials/{material}/comparisons")
def comparisons(material: str):
    return _run(get_db().comparisons, material)


@app.get("/schema")
def schema():
    return get_db().schema()


class SQLRequest(BaseModel):
    query: str
    limit: int = 200


@app.post("/sql")
def sql(req: SQLRequest):
    return _run(get_db().sql, req.query, req.limit)
