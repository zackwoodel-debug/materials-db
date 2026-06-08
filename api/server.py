"""FastAPI server exposing the MatChat RAG pipeline."""

import sqlite3
import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.ml.retriever import retrieve
from src.ml.chat_engine import answer

_ROOT = Path(__file__).resolve().parent.parent
_DB = str(_ROOT / "data" / "materials.db")

app = FastAPI(title="MatChat", description="RAG chat over materials-db")


class ChatRequest(BaseModel):
    query: str


class SimulateRequest(BaseModel):
    material: str
    thickness_nm: float
    substrate: str


@app.get("/health")
def health():
    """
    Physical purpose: Report whether the database is reachable and how many optical rows it contains, letting clients detect an uninitialised deployment before sending chat queries.
    Args/Returns: no parameters; returns {"status": "ok", "db_rows": int} or HTTP 503 with an error message if data/materials.db is absent.
    """
    if not Path(_DB).exists():
        return JSONResponse(
            status_code=503,
            content={"error": "Database not found. Run init_db.py first."},
        )

    conn = sqlite3.connect(_DB)
    db_rows = conn.execute("SELECT COUNT(*) FROM optical_nk").fetchone()[0]
    conn.close()
    return {"status": "ok", "db_rows": db_rows}


@app.post("/chat")
def chat(req: ChatRequest):
    """
    Physical purpose: Accept a natural language query, retrieve matching rows from the database, and return a model response grounded exclusively in those rows.
    Args/Returns: req.query — user question string; returns {"response": str, "sources": list[str]} where sources are the unique material names whose rows informed the answer.
    """
    rows = retrieve(req.query)
    response = answer(req.query, rows)

    # Collect unique material names in the order they first appear so the
    # caller knows which materials the model drew on.
    seen: set[str] = set()
    sources: list[str] = []
    for row in rows:
        name = row.get("material_name", "")
        if name and name not in seen:
            seen.add(name)
            sources.append(name)

    return {"response": response, "sources": sources}


@app.post("/simulate")
def simulate(req: SimulateRequest):
    """
    Physical purpose: Validate that the requested material exists in the database, then delegate a Parratt XRR simulation to the calculators CLI and return the output path alongside the data sources.
    Args/Returns: req.material — material name string; req.thickness_nm — film thickness in nm; req.substrate — substrate material name string; returns {"plot_path": str, "sources": list} or HTTP 404 if the material is unknown, HTTP 504 on timeout.
    """
    rows = retrieve(req.material)
    if not rows:
        return JSONResponse(
            status_code=404,
            content={"error": "Material not found in database."},
        )

    try:
        result = subprocess.run(
            [
                "python", "calculators/simulate_xrr.py",
                "--material", req.material,
                "--thickness", str(req.thickness_nm),
                "--substrate", req.substrate,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(_ROOT),
        )
    except subprocess.TimeoutExpired:
        return JSONResponse(
            status_code=504,
            content={"error": "Simulation timed out."},
        )

    sources = [r["source_ref"] for r in rows]
    return {"plot_path": result.stdout.strip(), "sources": sources}
