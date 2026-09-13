"""Tests for src/materials_db/launcher/modalfit_bridge.py.

The clone-resolution and pin-check logic is tested directly (no Tkinter
or real ModalFit clone needed). launch()'s WIRING (import-by-path,
monkeypatch the file dialog, call the load method, enter the event loop)
is tested against a minimal stand-in module that mimics
ModelPredictorApp's shape without needing a real Tk display -- this
environment's default Python has no _tkinter binding at all (see the
launcher's own verification report), so a test depending on a real
ModelPredictorApp would be unconditionally skipped here and never
actually run in CI. The real, empirical, real-Tk confirmation was done
once by hand (see modalfit_bridge.py's own docstring) and is not
re-derived as an automated test.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import materials_db.launcher.modalfit_bridge as bridge  # noqa: E402
from materials_db.launcher.modalfit_bridge import (  # noqa: E402
    ModalFitBridgeError, check_tk_version, launch, locate_modalfit_clone, verify_pin_or_warn,
)


class TestCheckTkVersion:
    """check_tk_version() guards against a real, confirmed failure: on Tk
    8.5 (Apple's bundled /usr/bin/python3), ModalFit's window renders as
    a genuinely blank white rectangle with no error at all -- found on a
    real desktop run of this launcher. Tested by injecting a fake
    tkinter module into sys.modules (this dev environment's own default
    Python has no tkinter at all, so the real module can't be
    monkeypatched directly -- see the ImportError-path test below, which
    exercises that real condition without needing to fake anything)."""

    @pytest.fixture
    def fake_tkinter(self, monkeypatch):
        import types
        fake = types.ModuleType("tkinter")
        fake.TkVersion = 8.5

        def _set(version):
            fake.TkVersion = version

        monkeypatch.setitem(sys.modules, "tkinter", fake)
        return _set

    def test_raises_below_minimum(self, fake_tkinter):
        fake_tkinter(8.5)
        with pytest.raises(ModalFitBridgeError, match=r"Tk is version 8\.5.*needs Tk >= 8\.6"):
            check_tk_version()

    def test_passes_at_minimum(self, fake_tkinter):
        fake_tkinter(8.6)
        check_tk_version()  # must not raise

    def test_passes_above_minimum(self, fake_tkinter):
        fake_tkinter(9.0)
        check_tk_version()  # must not raise

    def test_missing_tkinter_entirely_raises_a_clear_error(self, monkeypatch):
        """This dev environment's actual default Python has no tkinter
        at all -- exercised directly, not simulated, by removing any
        cached tkinter module and letting the real import fail."""
        monkeypatch.delitem(sys.modules, "tkinter", raising=False)
        with pytest.raises(ModalFitBridgeError, match="no Tk support at all"):
            check_tk_version()


class TestLocateModalfitClone:
    def test_no_path_and_no_env_var_raises(self, monkeypatch):
        monkeypatch.delenv("MODALFIT_PATH", raising=False)
        with pytest.raises(ModalFitBridgeError, match="No ModalFit clone configured"):
            locate_modalfit_clone()

    def test_explicit_path_without_model_predictor_raises(self, tmp_path):
        with pytest.raises(ModalFitBridgeError, match="not a ModalFit clone"):
            locate_modalfit_clone(str(tmp_path))

    def test_explicit_path_with_model_predictor_resolves(self, tmp_path):
        (tmp_path / "model_predictor.py").write_text("# stub\n")
        resolved = locate_modalfit_clone(str(tmp_path))
        assert resolved == tmp_path.resolve()

    def test_env_var_fallback(self, tmp_path, monkeypatch):
        (tmp_path / "model_predictor.py").write_text("# stub\n")
        monkeypatch.setenv("MODALFIT_PATH", str(tmp_path))
        resolved = locate_modalfit_clone()
        assert resolved == tmp_path.resolve()


class TestVerifyPinOrWarn:
    def test_non_git_directory_warns_without_raising(self, tmp_path):
        (tmp_path / "model_predictor.py").write_text("# stub\n")
        msg = verify_pin_or_warn(tmp_path)
        assert "WARNING" in msg
        assert "not a git repo" in msg


class TestLaunchWiring:
    """A stand-in for ModalFit's model_predictor.py: same shape (a
    filedialog-like object, an App class with after()/_load_model()/
    mainloop()), no Tkinter involved. Confirms launch() imports the
    module by file path, monkeypatches the dialog, DEFERS _load_model()
    via app.after() rather than calling it synchronously, and only then
    enters the event loop -- the exact sequence a real blank-window bug
    (found on a real desktop run) showed was necessary (see
    modalfit_bridge.py's docstring). The stub records what happened to a
    marker file rather than an in-memory attribute, since launch() never
    hands the constructed app back to the caller (matching the real
    ModelPredictorApp, which is fully owned by its own event loop once
    launched)."""

    @pytest.fixture
    def fake_modalfit_clone(self, tmp_path):
        marker = tmp_path / "calls.log"
        stub = tmp_path / "model_predictor.py"
        stub.write_text(
            "from pathlib import Path\n"
            f"_MARKER = Path(r'{marker}')\n"
            "\n"
            "class _FakeDialog:\n"
            "    @staticmethod\n"
            "    def askopenfilename(*a, **k):\n"
            "        raise AssertionError('real dialog should never be called -- must be patched')\n"
            "\n"
            "filedialog = _FakeDialog()\n"
            "\n"
            "class ModelPredictorApp:\n"
            "    def after(self, delay, callback):\n"
            "        # Real Tk defers callback until mainloop() is pumping;\n"
            "        # the fake just needs launch() to have scheduled\n"
            "        # (not called synchronously) before mainloop().\n"
            "        with open(_MARKER, 'a') as f:\n"
            "            f.write('after_scheduled\\n')\n"
            "        self._pending = callback\n"
            "\n"
            "    def _load_model(self):\n"
            "        path = filedialog.askopenfilename()\n"
            "        with open(_MARKER, 'a') as f:\n"
            "            f.write(f'loaded:{path}\\n')\n"
            "\n"
            "    def mainloop(self):\n"
            "        # Simulate the event loop firing the scheduled callback.\n"
            "        self._pending()\n"
            "        with open(_MARKER, 'a') as f:\n"
            "            f.write('mainloop\\n')\n"
        )
        return tmp_path, marker

    def test_launch_defers_load_via_after_then_enters_event_loop(self, fake_modalfit_clone, monkeypatch):
        """The order matters and is the point of this test: after_scheduled
        must come from launch() calling app.after(...) BEFORE mainloop()
        runs, not from _load_model() being called synchronously first --
        the correct pattern for GUI work regardless of what actually
        caused the real blank-white-window bug (confirmed separately to
        be an old Tk version, not this ordering -- see check_tk_version()
        and modalfit_bridge.py's module docstring). "loaded:..." only
        appears once the fake's mainloop() actually fires the scheduled
        callback, matching how a real Tk event loop would. check_tk_version
        is patched out here -- this test is about the after()/mainloop()
        sequence, not the Tk-version guard (covered separately in
        TestCheckTkVersion), and this dev environment's own Python has no
        tkinter at all."""
        monkeypatch.setattr(bridge, "check_tk_version", lambda: None)
        clone_path, marker = fake_modalfit_clone
        model_path = clone_path / "my_model.json"
        model_path.write_text("{}")

        # The fake's own askopenfilename raises if called unpatched -- a
        # clean run here proves launch() really monkeypatches it rather
        # than letting a real dialog block.
        launch(model_path, clone_path)

        lines = marker.read_text().splitlines()
        assert lines == ["after_scheduled", f"loaded:{model_path}", "mainloop"]
