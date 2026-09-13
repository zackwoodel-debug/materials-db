#!/usr/bin/env bash
# scripts/launch_modalfit_pick_stack.command
# ===============================================
# Double-click this file in Finder to run the INTERACTIVE stack-picker
# launcher: search materials_oxide_test.db, pick an ambient/film(s)/
# substrate, and ModalFit opens with that one finished stack pre-loaded,
# ready to predict/fit. Answers a few prompts in the Terminal window this
# opens.
#
# Want ModalFit to just open, ready to browse/build with NO prompts at
# all? Double-click scripts/launch_modalfit.command instead -- it opens
# ModalFit's own stack-BUILDER tool with the whole materials library
# pre-loaded into its native picker.
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
