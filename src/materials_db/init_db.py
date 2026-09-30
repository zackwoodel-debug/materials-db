#!/usr/bin/env python3
"""
init_db.py -- DEPRECATED; does nothing but explain itself.

It used to rebuild the legacy data/materials.db in four steps (core/schema.sql; pipeline/fetch_optical_data.py, which cloned
refractiveindex.info and repopulated the optical tables; core/seed_manual.sql; core/audit.py). Its step paths predate the src/
layout, so since the June 2026 src/ migration it aborted at step 1. It is deliberately not repaired: a working version would
fetch from the network and rewrite the legacy database that verify_all.py and the guard tests read.

The maintained database is the release, built offline from the committed inputs:
    python3 scripts/build_release.py --version X.Y.Z
(see README "Downloadable dataset" and docs/installation.md).
"""
import sys

MESSAGE = ("materials_db.init_db is deprecated and does nothing: it rebuilt the legacy data/materials.db and has been broken "
           "since the src/ migration. Build the maintained database with `python3 scripts/build_release.py --version X.Y.Z` "
           "(see README, 'Downloadable dataset').")


def main():
    sys.exit(MESSAGE)


if __name__ == "__main__":
    main()
