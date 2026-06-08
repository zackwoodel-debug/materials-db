#!/bin/bash

MODEL="qwen2.5-coder:7b"

if ! git rev-parse --is-inside-work-tree &>/dev/null; then
  echo "❌ Not a git repository." && exit 1
fi

git add .

if git diff --cached --quiet; then
  echo "❌ Nothing to commit." && exit 1
fi

if ! curl -s http://localhost:11434/api/tags &>/dev/null; then
  echo "❌ Ollama is not running. Start it with: ollama serve" && exit 1
fi

echo "🤖 Analyzing changes with Ollama ($MODEL)..."

SYSTEM_PROMPT="You are a zero-inference git commit assistant. Analyze the diff and output exactly one conventional commit message. Format: <type>(<scope>): <description>. Allowed types: feat fix docs style refactor test chore. Rules: (1) Base the message 100% on literal lines added, modified, or deleted — do not infer intent, guess reasons, or extrapolate beyond what the diff shows. (2) Treat mathematical constants, bitmasks, hardware registers, and domain-specific terms with exact precision — do not round, truncate, or define them. (3) Write the description in lowercase imperative mood, no trailing period. (4) Output ONLY the raw commit string — no markdown, no backticks, no intro text, no explanation."

GIT_DIFF=$(git diff --cached)

JSON_PAYLOAD=$(jq -n \
  --arg model "$MODEL" \
  --arg system "$SYSTEM_PROMPT" \
  --arg prompt "$GIT_DIFF" \
  '{model:$model, system:$system, prompt:$prompt, stream:false, options:{temperature:0.1, num_ctx:8192}}')

RESPONSE=$(curl -s -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d @- <<< "$JSON_PAYLOAD")

PROPOSED=$(echo "$RESPONSE" | jq -r '.response // empty' 2>/dev/null \
  | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')

if [ -z "$PROPOSED" ] || [ "$PROPOSED" = "null" ]; then
  echo "❌ No response from Ollama. Is $MODEL pulled?"
  echo "   API response: $RESPONSE"
  exit 1
fi

echo -e "\n📝 Proposed message:"
echo "────────────────────────────────"
echo -e "\033[1;32m$PROPOSED\033[0m"
echo "────────────────────────────────"

read -rp "Commit? (y/n/e to edit): " choice
case "$choice" in
  y|Y) git commit -m "$PROPOSED" ;;
  e|E) git commit -e -m "$PROPOSED" ;;
  *)   echo "❌ Aborted." ;;
esac
