"""Natural-language-to-SQL agent with grounded answer generation.

Stack-building detection is layered on top of the SQL path: if the question
matches _STACK_TRIGGER the agent skips SQL entirely and calls build_stack,
returning a markdown summary table + the written JSON path.
"""

import json
import logging
import os
import re
import sqlite3
from datetime import date
from pathlib import Path

from materials_db.core.schema import get_schema_summary

log = logging.getLogger(__name__)

# ── Prompt templates ──────────────────────────────────────────────────────────

_SQL_SYSTEM = """\
You are a materials science SQL expert.
Schema: {schema_summary}
Rules:
- Output exactly one SELECT query, nothing else.
- Never invent values. If data is missing, output: SELECT 'no_data'.
- Prefer materials_flat view for simple property lookups.
- Always match material names with LIKE, e.g. WHERE m.name LIKE '%PMMA%', never exact equality.
- When a wavelength is given, use BETWEEN (wavelength - 10) AND (wavelength + 10) to tolerate minor offsets.
- When querying optical_nk, always JOIN with materials: JOIN materials m ON o.material_id = m.id."""

_ANSWER_SYSTEM = """\
You are a materials science assistant.
Answer based ONLY on the SQL results provided.
Never invent properties, values, or units.
If results are empty or contain no relevant data, respond with exactly:
I do not have data on that."""

# ── Stack-building helpers ────────────────────────────────────────────────────

_STACK_TRIGGER = re.compile(
    r"\b(?:build|create|make|generate|assemble|export)\b.{0,80}\bstack\b"
    r"|\bstack\s+of\b"
    r"|\bstack\s+with\b",
    re.IGNORECASE | re.DOTALL,
)

_T_NM  = re.compile(r"(\d+(?:\.\d+)?)\s*nm\b",                    re.IGNORECASE)
_T_ANG = re.compile(r"(\d+(?:\.\d+)?)\s*(?:Å|ang(?:strom)?)\b",  re.IGNORECASE)
_T_UM  = re.compile(r"(\d+(?:\.\d+)?)\s*(?:μm|um|micron)\b",     re.IGNORECASE)

_SUBSTRATE_HINTS: frozenset[str] = frozenset(
    {"qcm", "sensor", "crystal", "substrate", "wafer", "quartz"}
)

_MATERIAL_NAMES: dict[str, str] = {
    "polystyrene": "Polystyrene",
    "ps": "Polystyrene",
    "gold": "Gold",
    "au": "Gold",
    "chromium": "Chromium",
    "cr": "Chromium",
    "silicon": "Silicon",
    "si": "Silicon",
    "silica": "SiO2",
    "sio2": "SiO2",
    "quartz": "quartz",
    "qcm sensor": "quartz",
    "qcm crystal": "quartz",
    "qcm": "quartz",
    "pmma": "PMMA",
    "poly(methyl methacrylate)": "PMMA",
    "titanium": "Titanium",
    "ti": "Titanium",
    "pdms": "PDMS",
    "peg": "PEG",
    "water": "Water",
    "d2o": "D2O",
    "dppc": "DPPC",
}


def _is_stack_request(question: str) -> bool:
    return bool(_STACK_TRIGGER.search(question))


def _thickness_to_ang(text: str) -> float | None:
    """Return the first thickness value found in *text*, converted to Å."""
    m = _T_NM.search(text)
    if m:
        return float(m.group(1)) * 10.0
    m = _T_ANG.search(text)
    if m:
        return float(m.group(1))
    m = _T_UM.search(text)
    if m:
        return float(m.group(1)) * 1e4
    return None


def _resolve_mat(raw: str) -> str:
    """Map a raw material string to a canonical name for build_stack."""
    lower = raw.strip().lower()
    if lower in _MATERIAL_NAMES:
        return _MATERIAL_NAMES[lower]
    for key, val in _MATERIAL_NAMES.items():
        if key in lower:
            return val
    return raw.strip().title()


def _parse_stack_question(question: str) -> list[dict] | None:
    """Parse natural-language or colon-notation layer specs from a question.

    Supported inputs
    ----------------
    - Colon notation : ``Polystyrene:1000,Gold:50,quartz``
      (thickness in Å; last entry becomes substrate)
    - Natural language: ``100nm polystyrene on 50nm gold on a QCM sensor``
      (thickness unit detected; last entry containing a substrate hint becomes
      substrate)

    Returns a layer list for build_stack, or None when the question cannot
    be parsed well enough to attempt a build.
    """
    # ── Colon notation ────────────────────────────────────────────────────────
    colon_hits = re.findall(r"([\w][\w\s]*?)\s*:\s*(\d+(?:\.\d+)?)", question)
    if len(colon_hits) >= 2:
        layers: list[dict] = []
        for mat_raw, thick_str in colon_hits:
            mat = _resolve_mat(mat_raw)
            layers.append({"material": mat, "thickness": float(thick_str)})
        # Last layer → substrate
        layers[-1]["substrate"] = True
        layers[-1].pop("thickness", None)
        return layers

    # ── "X on Y on Z" natural language ───────────────────────────────────────
    # Strip the trigger phrase so "build me a stack of 100nm PS on Gold on quartz"
    # becomes "100nm PS on Gold on quartz".
    stripped = _STACK_TRIGGER.sub("", question, count=1).strip()
    stripped = re.sub(r"^[\s:,of]+", "", stripped, flags=re.IGNORECASE).strip()

    if "on" not in stripped.lower():
        return None

    segments = re.split(r"\s+on\s+", stripped, flags=re.IGNORECASE)
    layers = []
    for seg in segments:
        seg = seg.strip().strip(",").strip()
        if not seg:
            continue
        thick = _thickness_to_ang(seg)
        # Remove thickness tokens to isolate the material name
        seg_clean = _T_NM.sub("", seg)
        seg_clean = _T_ANG.sub("", seg_clean)
        seg_clean = _T_UM.sub("", seg_clean)
        seg_clean = re.sub(r"\b(?:a|an|the)\b", "", seg_clean, flags=re.IGNORECASE)
        seg_clean = seg_clean.strip()
        if not seg_clean:
            continue
        mat = _resolve_mat(seg_clean)
        is_sub = any(h in seg_clean.lower() for h in _SUBSTRATE_HINTS)
        layer: dict = {"material": mat}
        if thick is not None and not is_sub:
            layer["thickness"] = thick
        if is_sub:
            layer["substrate"] = True
        layers.append(layer)

    return layers if len(layers) >= 2 else None


def _make_summary_table(sf) -> str:
    """Return a GitHub-flavoured markdown table summarising *sf*."""
    header = "| # | Role | Material | Thickness (Å) | n@633 nm | X-ray SLD (Å⁻²) |"
    sep    = "|---|------|----------|:-------------:|:--------:|:---------------:|"
    lines  = [header, sep]
    for i, layer in enumerate(sf.stack):
        role = layer.role or "film"
        mat  = layer.label
        t    = "—"
        if layer.structural and layer.structural.thickness:
            t = f"{layer.structural.thickness.value:.1f}"
        n_val  = "—"
        sld_val = "—"
        if layer.molecular:
            if layer.molecular.n_at_633nm is not None:
                n_val = f"{layer.molecular.n_at_633nm:.4f}"
            if layer.molecular.xray_sld_A2_CuKa is not None:
                sld_val = f"{layer.molecular.xray_sld_A2_CuKa:.3e}"
        lines.append(f"| {i} | {role} | {mat} | {t} | {n_val} | {sld_val} |")
    return "\n".join(lines)


# ── Validation ────────────────────────────────────────────────────────────────

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|PRAGMA)\b",
    re.IGNORECASE,
)


def _extract_sql(text: str) -> str:
    """
    Physical purpose: Strip markdown code fences so the raw SQL string can be passed directly to sqlite3 without syntax errors.
    Args/Returns: text — raw LLM output string; returns the first SQL statement found, without fences or trailing semicolons.
    """
    match = re.search(r"```(?:sql)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip().split(";")[0].strip()
    return text.strip().split(";")[0].strip()


def _validate_sql(sql: str) -> bool:
    """
    Physical purpose: Ensure the SQL is a read-only SELECT containing none of the keywords that would modify or expose DB structure, protecting the database from writes or privilege escalation.
    Args/Returns: sql — SQL string to inspect; returns True only when the statement starts with SELECT and contains no forbidden keyword.
    """
    if not sql.strip().upper().startswith("SELECT"):
        return False
    return not bool(_FORBIDDEN.search(sql))


def _tables_from_sql(sql: str) -> list[str]:
    """
    Physical purpose: Extract table and view names from a SQL string so the caller can surface which sources contributed to the answer.
    Args/Returns: sql — SQL query string; returns a deduplicated list of identifiers found after FROM or JOIN keywords.
    """
    matches = re.findall(r"(?:FROM|JOIN)\s+(\w+)", sql, re.IGNORECASE)
    return list(dict.fromkeys(matches))


def _confidence(sql: str, rows: list) -> str:
    """
    Physical purpose: Classify how directly the query result answers the user question so the UI can render an appropriate confidence badge.
    Args/Returns: sql — executed SQL string; rows — result row list; returns 'no_data', 'approximate', or 'exact_match'.
    """
    if not rows:
        return "no_data"
    if re.search(r"\bLIKE\b|\bBETWEEN\b", sql, re.IGNORECASE):
        return "approximate"
    return "exact_match"


def _clean_messages(history: list[dict], question: str) -> list[dict]:
    """
    Physical purpose: Sanitise the conversation history into a valid Anthropic/OpenAI message list — only user and assistant roles, alternating, ending with the current user question.
    Args/Returns: history — raw history list from the client; question — current question string; returns a well-formed messages list.
    """
    valid = {"user", "assistant"}
    cleaned: list[dict] = []
    for turn in history:
        role = turn.get("role", "")
        content = str(turn.get("content", "")).strip()
        if role in valid and content:
            # Merge consecutive same-role turns by skipping duplicates.
            if not cleaned or cleaned[-1]["role"] != role:
                cleaned.append({"role": role, "content": content})
    # Anthropic requires the first message to be from the user.
    while cleaned and cleaned[0]["role"] != "user":
        cleaned.pop(0)
    cleaned.append({"role": "user", "content": question})
    return cleaned


# ── Agent ─────────────────────────────────────────────────────────────────────

class SQLAgent:
    """Converts natural-language questions to SQL, executes them read-only, and returns grounded answers."""

    def __init__(self, db_path: str) -> None:
        """
        Physical purpose: Open database connections, build the compact schema summary, and configure the LLM client for either Anthropic or Ollama depending on the OLLAMA environment variable.
        Args/Returns: db_path — absolute or relative path to the SQLite file; raises FileNotFoundError if absent.
        """
        if not Path(db_path).exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        self._db_path = Path(db_path).resolve()

        # Writable connection for one-time VIEW creation and schema introspection.
        _setup = sqlite3.connect(db_path)
        self.schema_summary = get_schema_summary(_setup)
        _setup.close()

        # Read-only connection used for all query execution.
        self._conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row

        # ── LLM backend swap: Anthropic cloud → local Ollama (openai-compatible) ──
        from openai import OpenAI  # noqa: PLC0415
        self._model: str = os.environ.get("OLLAMA_MODEL", "llama3.1")
        self._client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

    def _call_llm(self, system: str, messages: list[dict], max_tokens: int = 512) -> str:
        """
        Physical purpose: Dispatch a completion request to whichever backend is configured, abstracting the Anthropic and OpenAI wire formats behind a single call site.
        Args/Returns: system — system prompt string; messages — role/content message list; max_tokens — reply token ceiling; returns the model's text output stripped of leading/trailing whitespace.
        """
        resp = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}] + messages,
        )
        return (resp.choices[0].message.content or "").strip()

    def _build_stack_answer(self, question: str) -> dict:
        """Parse *question* for layer specs, call build_stack, write JSON, return summary.

        Returns a response dict with the same keys as ask() plus two extras:
        ``stack_path`` (absolute path of the written file) and ``stack_json``
        (the StackFile as a plain dict ready for serialisation).
        """
        from materials_db.pipeline.stack_exporter import build_stack  # local import: avoids circular dep at module level

        layers = _parse_stack_question(question)
        if not layers:
            return {
                "answer": (
                    "I could not parse a layer specification from your question.\n\n"
                    "Try one of these formats:\n"
                    "- `build a stack of Polystyrene:1000,Gold:50,quartz`  (thickness in Å)\n"
                    "- `build me a stack of 100nm polystyrene on 50nm gold on a QCM sensor`"
                ),
                "sql": "",
                "rows": [],
                "tables_used": [],
                "confidence": "no_data",
            }

        # Infer a human-readable sample_id from the film material names.
        film_mats = [l["material"] for l in layers if not l.get("substrate")]
        sample_id = "-".join(m.replace(" ", "_") for m in film_mats[:2]) or "stack"

        try:
            sf = build_stack(
                layers,
                sample_id=sample_id,
                user="chat",
                proposal_id="chat",
                db_path=self._db_path,
            )
        except Exception as exc:
            log.warning("build_stack failed: %s", exc)
            return {
                "answer": f"Stack build failed: {exc}",
                "sql": "",
                "rows": [],
                "tables_used": [],
                "confidence": "no_data",
            }

        # Write JSON atomically to data/stacks/.
        out_dir = self._db_path.parent / "stacks"
        out_dir.mkdir(exist_ok=True)
        fname = f"{date.today().strftime('%Y%m%d')}_{sample_id}_slab_v1.json"
        out_path = out_dir / fname
        stack_dict = sf.model_dump(mode="json", exclude_none=True)
        content = json.dumps(stack_dict, indent=2, ensure_ascii=False)
        tmp = out_path.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, out_path)
        log.info("Stack written → %s", out_path)

        table = _make_summary_table(sf)
        answer = f"Stack built: **{sample_id}** → `{out_path}`\n\n{table}"

        return {
            "answer": answer,
            "sql": "",
            "rows": [],
            "tables_used": ["stack_exporter"],
            "confidence": "stack_built",
            "stack_path": str(out_path),
            "stack_json": stack_dict,
        }

    def ask(self, question: str, history: list[dict]) -> dict:
        """
        Physical purpose: Convert a natural-language question to SQL, execute it read-only, then produce an answer grounded exclusively in the returned rows.  Stack-building requests are intercepted before the SQL path and routed to _build_stack_answer.
        Args/Returns: question — user question string; history — prior conversation turns; returns dict with keys answer, sql, rows, tables_used, confidence (plus stack_path / stack_json for stack requests).
        """
        if _is_stack_request(question):
            return self._build_stack_answer(question)

        # Step a: inject schema into the SQL-generation system prompt.
        sql_system = _SQL_SYSTEM.format(schema_summary=self.schema_summary)

        # Step b: ask the LLM to produce a single SELECT query.
        messages = _clean_messages(history, question)
        raw = self._call_llm(sql_system, messages, max_tokens=256)
        sql = _extract_sql(raw)

        # Step c: reject any non-SELECT or destructive SQL before touching the DB.
        if not _validate_sql(sql):
            return {
                "answer": "I do not have data on that.",
                "sql": sql,
                "rows": [],
                "tables_used": [],
                "confidence": "no_data",
            }

        # Step d: execute against the read-only connection.
        try:
            cursor = self._conn.execute(sql)
            col_names = [desc[0] for desc in (cursor.description or [])]
            rows: list[dict] = [dict(zip(col_names, r)) for r in cursor.fetchall()]
        except Exception:
            return {
                "answer": "I do not have data on that.",
                "sql": sql,
                "rows": [],
                "tables_used": _tables_from_sql(sql),
                "confidence": "no_data",
            }

        # Treat SELECT 'no_data' sentinel as empty.
        if rows and all(v == "no_data" for row in rows for v in row.values()):
            rows = []

        # Step e: generate a grounded natural-language answer from the rows.
        answer_prompt = (
            f"Question: {question}\n"
            f"SQL: {sql}\n"
            f"Results: {json.dumps(rows, default=str)}"
        )
        answer = self._call_llm(
            _ANSWER_SYSTEM,
            [{"role": "user", "content": answer_prompt}],
            max_tokens=512,
        )

        # Step f: assemble the result dict.
        return {
            "answer": answer,
            "sql": sql,
            "rows": rows,
            "tables_used": _tables_from_sql(sql),
            "confidence": _confidence(sql, rows),
        }
