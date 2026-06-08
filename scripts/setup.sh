#!/bin/bash
set -e
echo "=== git-ai-commit setup ==="

if ! command -v jq &>/dev/null; then
  echo "Installing jq..."
  if command -v brew &>/dev/null; then brew install jq
  elif command -v apt &>/dev/null; then sudo apt install -y jq
  else echo "❌ Install jq manually: https://jqlang.github.io/jq/" && exit 1
  fi
fi

if ! command -v ollama &>/dev/null; then
  echo "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
fi

echo "Pulling qwen2.5-coder:7b (one-time, ~4GB)..."
ollama pull qwen2.5-coder:7b

mkdir -p ~/bin
cp git-ai-commit.sh ~/bin/git-ai-commit.sh
chmod +x ~/bin/git-ai-commit.sh

SHELL_RC="$HOME/.zshrc"
[ "$SHELL" = "/bin/bash" ] && SHELL_RC="$HOME/.bashrc"

grep -q 'export PATH="$HOME/bin:$PATH"' "$SHELL_RC" || \
  echo 'export PATH="$HOME/bin:$PATH"' >> "$SHELL_RC"

grep -q 'alias gcam=' "$SHELL_RC" || \
  echo 'alias gcam="~/bin/git-ai-commit.sh"' >> "$SHELL_RC"

echo ""
echo "✅ Done! Run: source $SHELL_RC"
echo "   Then use: gcam  (in any git repo)"
