"""FastAPI SQL-RAG server for materials.db."""

import json
import os
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from materials_db.core.audit import run_audit
from materials_db.core.sql_agent import SQLAgent

_ROOT = Path(__file__).resolve().parents[3]
_DB_PATH = str(_ROOT / "data" / "materials.db")

_agent: SQLAgent | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start-up: audit the DB and instantiate the agent; shut-down: close the DB connection."""
    global _agent
    if not run_audit():
        raise RuntimeError("DB audit failed — server will not start.")
    _agent = SQLAgent(_DB_PATH)
    yield
    if _agent is not None:
        _agent._conn.close()


app = FastAPI(title="MatChat SQL-RAG", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str
    history: list[dict] = []


@app.get("/health")
def health():
    """
    Physical purpose: Report database and server readiness so clients can detect an uninitialised or crashed backend before issuing chat queries.
    Args/Returns: no parameters; returns {status, db_rows, tables} on success or HTTP 503 if the agent is not ready.
    """
    if _agent is None:
        return JSONResponse(
            
            status_code=503,
            content={"status": "unavailable", "error": "Agent not initialised."},
        )

    try:
        conn = sqlite3.connect(_DB_PATH)

        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        db_rows = conn.execute("SELECT COUNT(*) FROM optical_nk").fetchone()[0]
        conn.close()
    except Exception as exc:
        return JSONResponse(status_code=503, content={"status": "error", "error": str(exc)})

    return {"status": "ok", "db_rows": db_rows, "tables": tables}


@app.post("/chat")
def chat(req: ChatRequest):
    """
    Physical purpose: Accept a natural-language materials science question, run it through the SQL agent, and return a database-grounded answer with the query, source tables, and confidence classification.
    Args/Returns: req.query — question string; req.history — prior conversation turns; returns {response, sql, sources, confidence}.
    """
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialised.")

    result = _agent.ask(req.query, req.history)

    resp = {
        "response": result["answer"],
        "sql": result["sql"],
        "sources": result["tables_used"],
        "confidence": result["confidence"],
    }
    # Stack-build results carry extra fields; pass them through without
    # changing the existing response contract for SQL queries.
    if "stack_path" in result:
        resp["stack_path"] = result["stack_path"]
    if "stack_json" in result:
        resp["stack_json"] = result["stack_json"]
    return resp


# ── /stack endpoint ────────────────────────────────────────────────────────────

class StackRequest(BaseModel):
    """Structured layer list for building a slab JSON v1 stack file.

    Each element of *layers* is passed directly to build_stack; at minimum it
    must contain a ``"material"`` key.  Mark the substrate layer with
    ``"substrate": true``.  Thickness and bounds are optional.

    Example body::

        {
          "layers": [
            {"material": "Polystyrene", "thickness": 1000},
            {"material": "Gold",        "thickness": 50},
            {"material": "quartz",      "substrate": true}
          ],
          "sample_id": "PS-on-Au",
          "user": "scientist",
          "proposal_id": "P2024-001"
        }
    """

    layers: list[dict]
    sample_id: str
    user: str = "api"
    proposal_id: str = ""
    out_dir: Optional[str] = None


@app.post("/stack")
def build_stack_endpoint(req: StackRequest):
    """Build a slab JSON v1 StackFile from a structured layer list.

    Physical purpose: Accept a fully-specified layer list, query materials.db
    for all optical/scattering/viscoelastic properties, assemble a StackFile,
    write it atomically to data/stacks/ (or a caller-specified directory), and
    return the JSON together with the written path.

    Args/Returns: req — StackRequest body; returns
    {stack_json, written_path, n_layers, sample_id} or HTTP 422 on error.
    """
    from materials_db.pipeline.stack_exporter import build_stack

    if not req.layers:
        raise HTTPException(status_code=422, detail="layers must not be empty.")

    try:
        sf = build_stack(
            req.layers,
            sample_id=req.sample_id,
            user=req.user,
            proposal_id=req.proposal_id,
            db_path=Path(_DB_PATH),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    stack_dict = sf.model_dump(mode="json", exclude_none=True)

    # Resolve output directory; default to data/stacks/ next to the DB.
    if req.out_dir is not None:
        out_dir = Path(req.out_dir)
    else:
        out_dir = _ROOT / "data" / "stacks"
    out_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().strftime("%Y%m%d")
    safe_id = req.sample_id.replace("/", "_").replace(" ", "_")
    fname = f"{today}_{safe_id}_slab_v1.json"
    out_path = out_dir / fname
    content = json.dumps(stack_dict, indent=2, ensure_ascii=False)
    tmp = out_path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, out_path)

    return {
        "stack_json": stack_dict,
        "written_path": str(out_path),
        "n_layers": sf.n_layers,
        "sample_id": sf.sample_id,
    }
