"""FastAPI SQL-RAG server for materials.db."""

import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

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

    return {
        "response": result["answer"],
        "sql": result["sql"],
        "sources": result["tables_used"],
        "confidence": result["confidence"],
    }
