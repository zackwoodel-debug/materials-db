#!/usr/bin/env bash
# scripts/launch_modalfit.command
# ===================================
# Double-click this file in Finder: ModalFit just opens, ready to use --
# no questions asked in the Terminal window this briefly shows. Opens
# ModalFit's own stack-BUILDER tool (slab_model_builder.py) with the
# whole materials-db catalog pre-loaded into its native "Load Library..."
# picker: click "+ Add Layer" -> "Apply from Library" to pick any of the
# 133 materials yourself, entirely inside ModalFit's own UI from there.
#
# Want to instead have THIS launcher search/pick a specific ambient/
# film(s)/substrate stack for you and hand ModalFit that one finished
# model, ready to predict/fit? Double-click
# scripts/launch_modalfit_pick_stack.command instead -- that one asks a
# few questions in the Terminal first.
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

"$VENV/bin/python3" "$ROOT/scripts/modalfit_builder_launcher.py" "$@"
status=$?

echo
if [ $status -ne 0 ]; then
  echo "Launcher exited with an error (see above)."
fi
read -r -p "Press Enter to close this window..."
exit $status
