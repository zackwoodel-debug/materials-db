#!/bin/bash
# Optional, personal tooling: git-ai-commit (commit messages drafted by a local Ollama model).
# Not needed to build, test or use materials-db, and never run in CI.
#
# This script only CHECKS prerequisites and prints the manual steps. It does not install software, download models,
# copy files into your home directory, or edit shell startup files. Do the steps yourself if you want the tool:
#
#   1. Install jq            https://jqlang.github.io/jq/          (e.g. brew install jq)
#   2. Install Ollama        https://ollama.com/download           (use the installer from the site; review it first)
#   3. Pull the model        ollama pull qwen2.5-coder:7b          (~4 GB, one-time)
#   4. Use the script        scripts/git-ai-commit.sh              (run it from inside a git repository;
#                                                                  add an alias or copy it onto your PATH if you like)
set -e
echo "=== git-ai-commit prerequisites (check only; nothing is installed or changed) ==="
missing=0
for tool in jq ollama; do
  if command -v "$tool" &>/dev/null; then echo "  found    $tool"; else echo "  missing  $tool"; missing=1; fi
done
if command -v ollama &>/dev/null && ! ollama list 2>/dev/null | grep -q "qwen2.5-coder:7b"; then
  echo "  missing  model qwen2.5-coder:7b   (ollama pull qwen2.5-coder:7b)"; missing=1
fi
if [ "$missing" -eq 1 ]; then
  echo "See the steps at the top of scripts/setup.sh."
  exit 1
fi
echo "Ready: run scripts/git-ai-commit.sh inside a git repository."
