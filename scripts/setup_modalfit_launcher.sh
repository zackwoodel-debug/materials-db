#!/usr/bin/env bash
# scripts/setup_modalfit_launcher.sh
# =====================================
# One-time setup for the double-click ModalFit launcher
# (scripts/launch_modalfit.command). Run this once (or again after a
# ModalFit re-clone, or if the launcher reports a Tk/dependency problem):
#
#   bash scripts/setup_modalfit_launcher.sh
#
# Does three things:
#   1. Finds a Python built with Tk >= 8.6. Required, not optional:
#      Apple's bundled system Python (/usr/bin/python3) ships Tk 8.5,
#      which renders ModalFit's window as a genuinely blank white
#      rectangle with no error at all -- found and documented the hard
#      way, see src/materials_db/launcher/modalfit_bridge.py's
#      check_tk_version(). This script refuses to silently fall back to
#      a Tk-8.5 Python and reproduce that same confusion.
#   2. Creates (or reuses) a local venv at .venv-modalfit-launcher/
#      (gitignored) with ModalFit's runtime dependencies installed.
#   3. Prompts for a local ModalFit clone path (git clone
#      https://github.com/agauer/modalfit) and saves it via
#      save_modalfit_path() to .modalfit_path (gitignored, repo-local) --
#      locate_modalfit_clone() reads this automatically from then on, so
#      a Finder double-click (which has no shell environment to read a
#      MODALFIT_PATH env var from) still finds it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv-modalfit-launcher"
CONFIG_FILE="$ROOT/.modalfit_path"

echo "ModalFit launcher setup"
echo "========================"
echo

# ---- 1. Find a Tk >= 8.6 Python ----------------------------------------

CANDIDATES=(
  "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
  "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
  "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
  "/opt/homebrew/bin/python3.13"
  "/opt/homebrew/bin/python3.12"
  "/opt/homebrew/bin/python3.11"
  "/usr/local/bin/python3"
  "python3"
)

PYBIN=""
for c in "${CANDIDATES[@]}"; do
  if command -v "$c" >/dev/null 2>&1; then
    ver="$("$c" -c 'import tkinter; print(tkinter.TkVersion)' 2>/dev/null || echo 0)"
    if awk -v v="$ver" 'BEGIN { exit !(v+0 >= 8.6) }'; then
      PYBIN="$(command -v "$c")"
      echo "Found Tk-$ver Python: $PYBIN"
      break
    fi
  fi
done

if [ -z "$PYBIN" ]; then
  echo "ERROR: no Python with Tk >= 8.6 found on this machine."
  echo
  echo "ModalFit's GUI needs Tk 8.6+. On an older Tk (notably Apple's bundled"
  echo "/usr/bin/python3, which ships Tk 8.5), its window renders as a genuinely"
  echo "blank white rectangle -- no error, nothing in stderr, just an empty window"
  echo "that never paints."
  echo
  echo "Install a python.org release (https://python.org/downloads -- these bundle"
  echo "a modern Tk) or run 'brew install python-tk', then re-run this script."
  exit 1
fi
echo

# ---- 2. Create/refresh the venv -----------------------------------------

if [ ! -d "$VENV" ]; then
  echo "Creating venv at $VENV ..."
  "$PYBIN" -m venv "$VENV"
else
  echo "Reusing existing venv at $VENV"
fi

echo "Installing dependencies ..."
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet numpy scipy matplotlib pandas refnx periodictable refellips
echo "Dependencies installed."
echo

# ---- 3. Locate and save the ModalFit clone path --------------------------

EXISTING=""
if [ -f "$CONFIG_FILE" ]; then
  EXISTING="$(cat "$CONFIG_FILE")"
fi

MFPATH=""
if [ -n "$EXISTING" ] && [ -f "$EXISTING/model_predictor.py" ]; then
  echo "Saved ModalFit path: $EXISTING"
  read -r -p "Keep using this path? [Y/n] " ans
  ans="${ans:-Y}"
  if [ "$ans" = "Y" ] || [ "$ans" = "y" ]; then
    MFPATH="$EXISTING"
  fi
fi

if [ -z "$MFPATH" ]; then
  echo "Need a local ModalFit clone (git clone https://github.com/agauer/modalfit somewhere)."
  read -r -p "Path to that clone: " MFPATH
  MFPATH="${MFPATH/#\~/$HOME}"
fi

if [ ! -f "$MFPATH/model_predictor.py" ]; then
  echo "ERROR: $MFPATH does not contain model_predictor.py -- not a ModalFit clone."
  exit 1
fi

"$VENV/bin/python3" -c "
import sys
sys.path.insert(0, '$ROOT/src')
from materials_db.launcher.modalfit_bridge import save_modalfit_path
save_modalfit_path('$MFPATH')
print('Saved ModalFit path to $CONFIG_FILE')
"

echo
echo "Checking the pin (src/materials_db/export/modalfit_contract.py) ..."
"$VENV/bin/python3" "$ROOT/scripts/verify_modalfit_pin.py" "$MFPATH" || true

echo
echo "Setup complete. Double-click scripts/launch_modalfit.command to run the launcher."
