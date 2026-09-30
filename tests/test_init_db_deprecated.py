"""materials_db.init_db is a deprecated stub: its only job is to stop the old pipeline (network fetch + rewrite of the legacy
data/materials.db) from running. Run it in a subprocess under a Python audit hook that records every network, database,
subprocess and file-write event, and prove it exits with the documented message having done none of them. A control run proves
the hook does record such events, so an empty record means something.
"""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from materials_db import init_db  # noqa: E402

HOOK = r'''
import atexit, json, os, sys
_LOG = os.environ["AUDIT_LOG"]
_WATCH = ("socket.", "sqlite3.", "subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.remove", "os.rename", "shutil.")
_events = []
def _hook(event, args):
    if event.startswith(_WATCH):
        _events.append([event, repr(args)[:200]])
    elif event == "open" and args and args[0] != _LOG:
        mode, flags = args[1], args[2] or 0
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            _events.append([event, repr(args)[:200]])
def _dump():
    with open(_LOG, "w") as f:
        json.dump(_events, f)
atexit.register(_dump)
sys.addaudithook(_hook)
'''

TRACKED_DBS = [ROOT / "data" / "materials.db", ROOT / "data" / "materials_oxide_test.db"]


def _audited_run(tmp_path, argv):
    hook_dir, work = tmp_path / "hook", tmp_path / "work"
    hook_dir.mkdir()
    work.mkdir()
    (hook_dir / "sitecustomize.py").write_text(HOOK)
    log = tmp_path / "audit.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    env.update(PYTHONPATH=os.pathsep.join([str(hook_dir), str(ROOT / "src")]), AUDIT_LOG=str(log))
    run = subprocess.run([sys.executable, *argv], cwd=work, env=env, capture_output=True, text=True, timeout=60)
    return run, json.loads(log.read_text()), sorted(p.name for p in work.iterdir())


def _digests():
    return {p.name: hashlib.sha1(p.read_bytes()).hexdigest() for p in TRACKED_DBS}


def test_init_db_exits_with_the_documented_message_and_touches_nothing(tmp_path):
    before = _digests()
    run, events, left_behind = _audited_run(tmp_path, ["-m", "materials_db.init_db"])
    assert run.returncode == 1
    assert run.stderr.strip() == init_db.MESSAGE and run.stdout == ""
    assert "scripts/build_release.py" in init_db.MESSAGE
    assert events == []  # no socket, sqlite3, subprocess or file-write event of any kind
    assert left_behind == []  # nothing written to its working directory
    assert _digests() == before  # neither tracked database was written


def test_the_audit_hook_does_record_database_network_and_write_events(tmp_path):
    probe = ("import sqlite3, socket, subprocess, sys\n"
             "sqlite3.connect('x.db').close()\n"
             "open('out.txt', 'w').close()\n"
             "try:\n    socket.create_connection(('127.0.0.1', 9), timeout=0.2)\nexcept OSError:\n    pass\n"
             "subprocess.run([sys.executable, '-c', 'pass'])\n")
    run, events, left_behind = _audited_run(tmp_path, ["-c", probe])
    assert run.returncode == 0, run.stderr
    kinds = {e for e, _ in events}
    assert {"sqlite3.connect", "open", "socket.connect", "subprocess.Popen"} <= kinds
    assert left_behind == ["out.txt", "x.db"]
