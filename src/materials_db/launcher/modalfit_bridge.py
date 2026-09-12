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

Environment caveat, not something to design around (found during that
same verification): in an automated/headless-ish session with no real
interactive desktop, a code path inside _load_model() (the diagram draw /
parameter-adjuster build, both matplotlib/Tk calls) blocked indefinitely
when the "Model loaded" confirmation dialog was suppressed rather than
shown normally. The UNPATCHED path (letting the real dialog show and get
naturally pumped by Tk's own event loop) completed cleanly on every real
run. launch() below therefore does NOT suppress that dialog -- do not
"fix" this by patching messagebox.showinfo away; on a real interactive
desktop session (where you already run ModalFit's GUI today) this hang
was not observed and is not expected to occur.
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


class ModalFitBridgeError(RuntimeError):
    """Raised for anything this bridge refuses to silently paper over: no
    clone configured, or the configured path isn't a ModalFit clone."""


def locate_modalfit_clone(explicit_path: Optional[str] = None) -> Path:
    """Resolve the ModalFit clone directory: an explicit path, else the
    MODALFIT_PATH environment variable, else raise with the exact fix --
    never guess a default path."""
    candidate = explicit_path or os.environ.get(MODALFIT_PATH_ENV_VAR)
    if not candidate:
        raise ModalFitBridgeError(
            f"No ModalFit clone configured. Pass --modalfit-path, or set the "
            f"{MODALFIT_PATH_ENV_VAR} environment variable to a local clone of "
            f"https://github.com/agauer/modalfit."
        )
    path = Path(candidate).expanduser().resolve()
    if not (path / "model_predictor.py").exists():
        raise ModalFitBridgeError(f"{path} does not contain model_predictor.py -- not a ModalFit clone.")
    return path


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
    until the user closes the ModalFit window."""
    mp = _import_model_predictor(clone_path)
    app = mp.ModelPredictorApp()
    with patch.object(mp.filedialog, "askopenfilename", return_value=str(model_json_path)):
        app._load_model()
    app.mainloop()
