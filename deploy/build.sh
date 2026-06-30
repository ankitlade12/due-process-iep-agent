#!/usr/bin/env bash
# Bundle the due_process package + the Qwen (openai) SDK + the handler into
# ./dist, the directory Function Compute uploads (see s.yaml `code: ./dist`).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DIST="$HERE/dist"

rm -rf "$DIST"
mkdir -p "$DIST"

# Install the project with the Qwen LLM extra (pulls in openai) into the bundle.
python3 -m pip install --quiet --upgrade --target "$DIST" "$HERE/..[llm]"

# Place the Function Compute handler at the bundle root.
cp "$HERE/handler.py" "$DIST/handler.py"

echo "Built deployment bundle at $DIST"
