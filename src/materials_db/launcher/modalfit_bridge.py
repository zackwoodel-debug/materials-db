"""launcher/modalfit_bridge.py
================================
Drives ModalFit's own, unmodified standalone desktop tool
(model_predictor.py) to launch pre-loaded with a generated slab-model
JSON -- a wrapper, not a fork. ModalFit's source is never edited; this
module dynamically imports model_predictor.py from a configured clone
path and calls its existing, real "Load Model" code path
(ModelPredictorApp._load_model(), the same method its own Load Model
button is bound to) with the file dialog monkeypatched in OUR process's
memory only, never touching ModalFit's files on disk.

Why model_predictor.py and not server.py (confirmed against the pinned
commit, see export/modalfit_contract.py's optical_nk_path_resolution
finding, and confirmed directly again for this module: server.py:69-112):
server.py's /api/model/upload route accepts exactly one JSON file and
never sets _json_dir, so a relative sidecar n,k CSV path (what
export_stack() writes) never resolves there. Only the standalone desktop
tool tracks the on-disk file location (model_predictor.py:549-552,
load_slab_model()) and can resolve a relative sidecar path.

Confirmed empirically before this module was written, not just read from
source: built a disposable venv with real Tk + ModalFit's actual
dependencies, exported a real Gold-on-silicon stack, and ran exactly the
sequence launch() below performs against the real ModelPredictorApp class
from the pinned clone -- the stack loaded correctly (3 entries, correct
roles, sidecar CSV resolved via _json_dir exactly as the contract
predicted).

Real environment gotcha, found on an actual desktop run of this launcher
(not a hang -- a silent mispaint, worse in a way, since nothing ever
errors): ModalFit's window came up a genuinely blank white rectangle,
consistently, across multiple runs. Isolated by ruling out every
materials-db-side variable one at a time -- reproduced with a bare,
unmodified `python3 model_predictor.py` (zero materials-db code
involved) -- down to the actual cause: Tk version. Apple's bundled
system Python (/usr/bin/python3, what a disposable venv built with
`python3 -m venv` naively inherits unless you pick the base interpreter
deliberately) ships Tk 8.5, which cannot render ModalFit's Tk/matplotlib
UI at all on this machine -- no exception, nothing in stderr, just an
empty window that never paints, on EVERY run, with or without a model
loaded. Rebuilding the exact same venv on a Tk-8.6 Python (a python.org
installer or a Homebrew "python-tk"-linked interpreter both work) with
identical dependencies fixed it immediately. check_tk_version() below
guards against this with a clear, actionable error instead of a silently
blank window -- see its docstring.
"""

import importlib.util
import os
import sys
from pathlib import Path
from typing import Optional
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT / "scripts"))
from verify_modalfit_pin import check_pin  # noqa: E402

MODALFIT_PATH_ENV_VAR = "MODALFIT_PATH"
MODALFIT_PATH_CONFIG_FILE = _ROOT / ".modalfit_path"
MIN_TK_VERSION = 8.6


class ModalFitBridgeError(RuntimeError):
    """Raised for anything this bridge refuses to silently paper over: no
    clone configured, the configured path isn't a ModalFit clone, or the
    running Python's Tk is too old to render ModalFit's GUI at all."""


def check_tk_version() -> None:
    """Raise ModalFitBridgeError if the CURRENT Python's Tk is older than
    MIN_TK_VERSION. This is a property of the Python/tkinter build
    actually running this code, not of the ModalFit clone directory --
    checked here because there is no other signal a caller would get:
    on Tk 8.5 (notably Apple's bundled /usr/bin/python3, and any venv
    built from it without picking a different base interpreter),
    ModalFit's window renders as a genuinely blank white rectangle, with
    no exception and nothing in stderr, every single time -- confirmed
    directly on this project's own desktop run (see this module's
    docstring). Failing loudly here, before ever opening a window a user
    would otherwise stare at wondering if the load silently failed, is
    strictly better than reproducing that confusion for the next person."""
    try:
        import tkinter
    except ImportError as e:
        raise ModalFitBridgeError(
            f"This Python has no Tk support at all ({e}) -- ModalFit's GUI cannot run. "
            f"Use a Python built with Tk support (a python.org installer or a Homebrew "
            f"python-tk-linked interpreter both work)."
        )
    if tkinter.TkVersion < MIN_TK_VERSION:
        raise ModalFitBridgeError(
            f"This Python's Tk is version {tkinter.TkVersion}, but ModalFit's GUI needs "
            f"Tk >= {MIN_TK_VERSION}. On an older Tk (notably Apple's bundled "
            f"/usr/bin/python3, which ships Tk 8.5), ModalFit's window renders as a "
            f"genuinely blank white rectangle -- no error, nothing in stderr, just an "
            f"empty window that never paints. Use a Python built against Tk 8.6+ instead "
            f"(a python.org installer or a Homebrew python-tk-linked interpreter both "
            f"work); check any candidate with: "
            f"python3 -c \"import tkinter; print(tkinter.TkVersion)\""
        )


def locate_modalfit_clone(explicit_path: Optional[str] = None) -> Path:
    """Resolve the ModalFit clone directory: an explicit path, else the
    MODALFIT_PATH environment variable, else a saved path from a prior
    save_modalfit_path() call (MODALFIT_PATH_CONFIG_FILE -- a plain-text,
    gitignored, repo-local file; see scripts/setup_modalfit_launcher.sh),
    else raise with the exact fix. Never guess a default path.

    The config-file fallback exists specifically for the double-click
    launcher (scripts/launch_modalfit.command): a Finder double-click has
    no shell environment to read MODALFIT_PATH from, and re-typing
    --modalfit-path every time defeats the point of double-clicking."""
    candidate = explicit_path or os.environ.get(MODALFIT_PATH_ENV_VAR)
    if not candidate and MODALFIT_PATH_CONFIG_FILE.exists():
        candidate = MODALFIT_PATH_CONFIG_FILE.read_text().strip()
    if not candidate:
        raise ModalFitBridgeError(
            f"No ModalFit clone configured. Pass --modalfit-path, set the "
            f"{MODALFIT_PATH_ENV_VAR} environment variable, or run "
            f"scripts/setup_modalfit_launcher.sh once to save a path -- "
            f"to a local clone of https://github.com/agauer/modalfit."
        )
    path = Path(candidate).expanduser().resolve()
    if not (path / "model_predictor.py").exists():
        raise ModalFitBridgeError(f"{path} does not contain model_predictor.py -- not a ModalFit clone.")
    return path


def save_modalfit_path(path) -> None:
    """Persist a ModalFit clone path to MODALFIT_PATH_CONFIG_FILE for
    locate_modalfit_clone() to pick up automatically next time (no env
    var, no --modalfit-path flag needed) -- used by
    scripts/setup_modalfit_launcher.sh's one-time setup."""
    resolved = Path(path).expanduser().resolve()
    if not (resolved / "model_predictor.py").exists():
        raise ModalFitBridgeError(f"{resolved} does not contain model_predictor.py -- not a ModalFit clone.")
    MODALFIT_PATH_CONFIG_FILE.write_text(str(resolved) + "\n")


def verify_pin_or_warn(clone_path: Path) -> str:
    """One-line status message; never raises -- an unpinned clone is a
    WARNING (per verify_modalfit_pin.py's own guidance: check whether the
    confirmed behaviors still hold), not a hard stop, since a newer clone
    that still happens to work is still worth launching."""
    try:
        result = check_pin(clone_path)
    except FileNotFoundError as e:
        return f"WARNING: {e} (not a git repo -- can't verify the pin, proceeding anyway)"
    if result["match"]:
        return f"Pin verified: {clone_path} is at the exact commit this launcher was checked against."
    return (f"WARNING: {clone_path} is at {result['actual_sha'][:12]}, not the pinned "
            f"{result['pinned_sha'][:12]}. Proceeding, but if the launch behaves "
            f"unexpectedly, run: python scripts/verify_modalfit_pin.py {clone_path}")


def _import_model_predictor(clone_path: Path):
    """Dynamically import model_predictor.py from an arbitrary clone path
    -- it's not a pip-installed package. Same importlib.util pattern
    already used in tests/test_export_all_materials_modalfit.py for
    loading a script by file path directly. model_predictor.py has no
    sibling-module imports of its own (confirmed by reading it: only
    stdlib + numpy/matplotlib/scipy/tkinter), so no sys.path changes are
    needed for it to import cleanly from an arbitrary directory."""
    spec = importlib.util.spec_from_file_location(
        "modalfit_model_predictor", clone_path / "model_predictor.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def launch(model_json_path, clone_path: Path) -> None:
    """Construct ModalFit's real ModelPredictorApp, pre-load it with
    model_json_path via the exact production _load_model() code path
    (the file dialog monkeypatched to return our path -- ModalFit's files
    on disk are never touched), and enter its GUI event loop. Blocks
    until the user closes the ModalFit window.

    Checks check_tk_version() FIRST -- see that function's docstring for
    why: the blank-white-window failure it guards against gives no other
    signal at all.

    _load_model() is deferred via app.after(0, ...) to fire once
    mainloop() has actually started, rather than being called
    synchronously beforehand: normally it runs as a button-click callback
    while the event loop is already pumping and the window is already
    mapped on screen, so calling it before mainloop() ever starts means
    the toplevel window has no valid on-screen surface yet when
    matplotlib's FigureCanvasTkAgg draws into it. This is a real, correct
    fix for a real ordering hazard -- confirmed NOT to be the (much
    larger) blank-window cause on its own, though: the same blank window
    still reproduced with this fix applied on a Tk-8.5 Python, and
    disappeared entirely on Tk 8.6 with or without this fix. Kept anyway
    because deferring GUI work until the event loop is actually running
    is the correct pattern regardless, and a real fit-adjacent bug (a
    live parameter edit scheduling a redraw before the window exists)
    is easy to imagine recurring even once check_tk_version() rules out
    the bigger failure mode."""
    check_tk_version()
    mp = _import_model_predictor(clone_path)
    app = mp.ModelPredictorApp()

    def _do_load():
        with patch.object(mp.filedialog, "askopenfilename", return_value=str(model_json_path)):
            app._load_model()

    app.after(0, _do_load)
    app.mainloop()
