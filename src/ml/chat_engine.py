"""Ollama-backed answer generator grounded in retrieved database rows."""

import json
import re

from openai import OpenAI

SYSTEM_PROMPT = (
    "You are a materials science assistant. Answer ONLY using the Facts provided.\n"
    "Do not invent properties, units, or values.\n"
    "If the answer is not in the Facts, respond with exactly:\n"
    "I do not have data on that in our database."
)

_FALLBACK = "I do not have data on that in our database."


def _numbers_grounded(response: str, facts_str: str) -> bool:
    """
    Physical purpose: Verify that every numeric token in the model response appears verbatim in the serialised facts string, so hallucinated physical values are caught before they reach the caller.
    Args/Returns: response — raw model output string; facts_str — json.dumps of the retrieved rows; returns True only when all numbers in the response can be found as substrings of facts_str.
    """
    numbers = re.findall(r"\b\d+(?:\.\d+)?\b", response)
    return all(num in facts_str for num in numbers)


def answer(query: str, rows: list[dict]) -> str:
    """
    Physical purpose: Send retrieved DB rows as grounding context to a local LLM and return its response, with a safety check that rejects any reply containing numbers absent from the provided facts.
    Args/Returns: query — user question string; rows — list[dict] of DB facts from the retriever; returns the model response string, or the standard fallback phrase if the response is empty or contains an ungrounded number.
    """
    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

    facts_str = json.dumps(rows)

    completion = client.chat.completions.create(
        model="llama3.1:8b",
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Facts:{facts_str}\nQuestion:{query}"},
        ],
    )

    response = (completion.choices[0].message.content or "").strip()

    # Reject the response if it is empty or if any number it contains is not
    # present in the grounding facts — either case signals a hallucination risk.
    if not response or not _numbers_grounded(response, facts_str):
        return _FALLBACK

    return response
