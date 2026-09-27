"""scripts/release_dictionary.py and the changelog rule: the dictionary describes exactly the schema (drift stops the build),
its vocabularies come from the data, and a versioned release needs its own CHANGELOG entry."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_release as br  # noqa: E402
import release_dictionary as rdict  # noqa: E402


def _schema_db():
    """An empty database with the release schema (every table the dictionary describes)."""
    c = sqlite3.connect(":memory:")
    for t, (_, cols) in rdict.TABLES.items():
        c.execute(f"CREATE TABLE {t} (" + ", ".join(f'"{col}"' for col in cols) + ")")
    c.execute("INSERT INTO chemical_descriptors(descriptor_json) VALUES ('{}')")
    return c


def test_every_described_table_and_column_builds():
    d = rdict.build(_schema_db(), "9.9.9")
    assert set(d["tables"]) == set(rdict.TABLES)
    assert all(c["description"] for t in d["tables"].values() for c in t["columns"])


def test_an_undescribed_column_stops_the_build():
    c = _schema_db()
    c.execute("ALTER TABLE materials ADD COLUMN mystery TEXT")
    with pytest.raises(rdict.DictionaryError, match="materials.mystery"):
        rdict.build(c, "9.9.9")


def test_a_described_column_that_vanished_stops_the_build():
    c = _schema_db()
    c.execute("DROP TABLE rheology")
    with pytest.raises(rdict.DictionaryError, match="rheology"):
        rdict.build(c, "9.9.9")


def test_versioned_release_needs_a_changelog_entry(tmp_path):
    log = tmp_path / "CHANGELOG.md"
    log.write_text("# Changelog\n\n## [1.2.3] - 2026-01-01\n")
    br.check_changelog("1.2.3", log)
    br.check_changelog("0.0.0-test", log)  # scratch / test builds are exempt
    with pytest.raises(br.ReleaseError, match=r"\[1.2.4\]"):
        br.check_changelog("1.2.4", log)


def test_the_repo_changelog_lists_every_published_tag_in_order():
    import re
    tags = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", (ROOT / "CHANGELOG.md").read_text(), re.M)
    assert tags[-1] == "0.1.0" and "0.13.0" in tags
    versions = [tuple(map(int, t.split("."))) for t in tags]
    assert versions == sorted(versions, reverse=True) and len(set(tags)) == len(tags)
