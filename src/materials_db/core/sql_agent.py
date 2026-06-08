"""Natural-language-to-SQL agent with grounded answer generation."""

import json
import os
import re
import sqlite3
from pathlib import Path

from materials_db.core.schema import get_schema_summary

# ── Prompt templates ──────────────────────────────────────────────────────────

_SQL_SYSTEM = """\
You are a materials science SQL expert.
Schema: {schema_summary}
Rules:
- Output exactly one SELECT query, nothing else.
- Never invent values. If data is missing, output: SELECT 'no_data'.
- Prefer materials_flat view for simple property lookups."""

_ANSWER_SYSTEM = """\
You are a materials science assistant.
Answer based ONLY on the SQL results provided.
Never invent properties, values, or units.
If results are empty or contain no relevant data, respond with exactly:
I do not have data on that."""

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

        # Writable connection for one-time VIEW creation and schema introspection.
        _setup = sqlite3.connect(db_path)
        self.schema_summary = get_schema_summary(_setup)
        _setup.close()

        # Read-only connection used for all query execution.
        self._conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
        self._conn.row_factory = sqlite3.Row

        self._use_ollama = bool(os.environ.get("OLLAMA"))
        if self._use_ollama:
            from openai import OpenAI  # noqa: PLC0415
            self._model: str = os.environ.get("OLLAMA_MODEL", "llama3.1")
            self._client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        else:
            import anthropic  # noqa: PLC0415
            self._model = "claude-haiku-4-5-20251001"
            self._client = anthropic.Anthropic()

    def _call_llm(self, system: str, messages: list[dict], max_tokens: int = 512) -> str:
        """
        Physical purpose: Dispatch a completion request to whichever backend is configured, abstracting the Anthropic and OpenAI wire formats behind a single call site.
        Args/Returns: system — system prompt string; messages — role/content message list; max_tokens — reply token ceiling; returns the model's text output stripped of leading/trailing whitespace.
        """
        if self._use_ollama:
            resp = self._client.chat.completions.create(
                model=self._model,
                temperature=0,
                messages=[{"role": "system", "content": system}] + messages,
            )
            return (resp.choices[0].message.content or "").strip()
        else:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return resp.content[0].text.strip()

    def ask(self, question: str, history: list[dict]) -> dict:
        """
        Physical purpose: Convert a natural-language question to SQL, execute it read-only, then produce an answer grounded exclusively in the returned rows.
        Args/Returns: question — user question string; history — prior conversation turns; returns dict with keys answer, sql, rows, tables_used, confidence.
        """
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
