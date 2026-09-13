#!/usr/bin/env bash
# scripts/launch_modalfit.command
# ===================================
# Double-click this file in Finder to run the ModalFit launcher --
# double-clicking a .command file opens Terminal.app and runs it as a
# shell script; that's the whole mechanism, no packaging magic involved.
#
# First run (no venv yet) triggers scripts/setup_modalfit_launcher.sh
# automatically. Re-run setup manually any time via:
#   bash scripts/setup_modalfit_launcher.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv-modalfit-launcher"

cd "$ROOT"

if [ ! -x "$VENV/bin/python3" ]; then
  echo "First-time setup needed (creating a venv with the right Python/Tk/dependencies)..."
  echo
  bash "$ROOT/scripts/setup_modalfit_launcher.sh"
  status=$?
  if [ $status -ne 0 ]; then
    echo
    echo "Setup did not complete -- see the error above."
    read -r -p "Press Enter to close this window..."
    exit $status
  fi
  echo
fi

"$VENV/bin/python3" "$ROOT/scripts/modalfit_launcher.py" "$@"
status=$?

echo
if [ $status -ne 0 ]; then
  echo "Launcher exited with an error (see above)."
fi
read -r -p "Press Enter to close this window..."
exit $status
