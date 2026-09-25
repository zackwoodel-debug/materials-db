#!/usr/bin/env python3
"""
scripts/fetch_source_dois.py
============================
Looks up a DOI on Crossref for every refractiveindex.info reference in the newest release that has none, and writes the
committed cache data/descriptors/source_dois.json that build_release.py applies offline.

A candidate is ACCEPTED only when all hold (nothing is guessed; the rest are recorded as rejected, with the reason):
  * the Crossref year equals the citation's year;
  * the first author's family name (Crossref) occurs in the citation's author text;
  * >= 90% of the Crossref title's words occur in our citation text (title or full citation string).
Reports, theses, datasheets and handbook chapters normally have no DOI and simply stay unmatched.

    python3 scripts/fetch_source_dois.py [--release release/materials-db-vX.Y.Z]
"""
import argparse
import json
import re
import sqlite3
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
OUT = _ROOT / "data" / "descriptors" / "source_dois.json"
UA = "materials-db DOI enrichment (https://github.com/zackwoodel-debug/materials-db)"
TITLE_COVERAGE = 0.90


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def citation_key(title, authors, year):
    """The key build_release.py uses to find a source's cached DOI."""
    return f"{norm(title)}|{norm(authors)}|{year or ''}"


def crossref(query, year):
    params = {"query.bibliographic": query, "rows": "5"}
    if year:
        params["filter"] = f"from-pub-date:{year},until-pub-date:{year}"
    req = urllib.request.Request("https://api.crossref.org/works?" + urllib.parse.urlencode(params), headers={"User-Agent": UA})
    for attempt in range(4):  # Crossref rate-limits bursts (HTTP 429/5xx): back off and retry
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)["message"]["items"]
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            time.sleep(2 ** attempt * 2)


def judge(item, title, authors, year):
    text = norm(f"{title} {authors}")
    words = [w for w in norm(" ".join(item.get("title") or [""])).split() if len(w) > 2]
    cov = sum(w in text.split() for w in words) / len(words) if words else 0.0
    cy = (item.get("issued", {}).get("date-parts") or [[None]])[0][0]
    fam = norm((item.get("author") or [{}])[0].get("family", ""))
    reasons = []
    if not year or cy != int(year):
        reasons.append(f"year {cy} != {year}")
    if not fam or fam not in norm(authors):
        reasons.append(f"first author '{fam}' not in citation")
    if cov < TITLE_COVERAGE:
        reasons.append(f"title coverage {cov:.2f} < {TITLE_COVERAGE}")
    return reasons, cov


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--release", type=Path, default=None)
    a = ap.parse_args(argv)
    sys.path.insert(0, str(_ROOT / "scripts"))
    from generate_ml_release_set import latest_release
    rel = a.release or latest_release()
    db = next(Path(rel).glob("materials-db-v*.sqlite"))
    rows = sqlite3.connect(str(db)).execute(
        "SELECT DISTINCT title, authors, year FROM sources WHERE (doi IS NULL OR doi = '') AND technique = 'refractiveindex.info'").fetchall()
    accepted, rejected = {}, {}
    for title, authors, year in rows:
        key = citation_key(title, authors, year)
        query = f"{title or ''} {authors or ''}".strip()
        try:
            items = crossref(query[:300], year)
        except Exception as e:  # network trouble: leave unmatched, never invent
            rejected[key] = dict(citation=query, reason=f"lookup failed: {type(e).__name__}")
            continue
        best = None
        for it in items:
            reasons, cov = judge(it, title, authors, year)
            cand = dict(doi=it.get("DOI"), crossref_title=(it.get("title") or [""])[0], title_coverage=round(cov, 3), reasons=reasons)
            if not reasons:
                best = cand
                break
            rejected.setdefault(key, dict(citation=query, candidates=[]))["candidates"].append(cand)
        if best:
            accepted[key] = dict(citation=query, doi=best["doi"].lower(), crossref_title=best["crossref_title"], title_coverage=best["title_coverage"])
            rejected.pop(key, None)
        time.sleep(1.0)
    OUT.write_text(json.dumps(dict(
        source="Crossref REST API (api.crossref.org); accepted only on year + first author + >=90% title-word match",
        retrieved_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), release=Path(rel).name,
        looked_up=len(rows), accepted=dict(sorted(accepted.items())), unmatched=dict(sorted(rejected.items()))), indent=1, ensure_ascii=False) + "\n")
    print(f"{len(rows)} citations without DOI: {len(accepted)} matched, {len(rejected)} unmatched -> {OUT.relative_to(_ROOT)}")
    for v in accepted.values():
        print(f"  + {v['doi']}  <- {v['citation'][:100]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
