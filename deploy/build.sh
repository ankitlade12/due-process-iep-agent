#!/usr/bin/env bash
# Bundle the due_process package + the Qwen (openai) SDK + the handler into
# ./dist, the directory Function Compute uploads (see s.yaml `code: ./dist`).
#
# Function Compute runs Linux x86_64 on Python 3.10, so the compiled
# dependencies (pydantic-core, jiter) must be Linux/cp310 wheels — NOT whatever
# your build machine happens to be. We fetch cross-platform wheels explicitly so
# this works even when you build on macOS.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DIST="$HERE/dist"
PYVER="3.10"

rm -rf "$DIST"
mkdir -p "$DIST"

# 1) Third-party deps (openai + its compiled deps) as Linux/cp310 wheels.
# NOTE: we install from a newer local Python, so pip evaluates environment
# markers (e.g. `python_version < "3.11"`) against the build machine, not the
# 3.10 target — which silently drops backports like exceptiongroup (needed by
# anyio on 3.10). List those explicitly so the bundle actually imports on FC.
python3 -m pip install --quiet --target "$DIST" \
  --platform manylinux2014_x86_64 \
  --python-version "$PYVER" --implementation cp --abi cp310 \
  --only-binary=:all: \
  openai exceptiongroup

# 2) Our own package is pure Python — install it without pulling deps again.
python3 -m pip install --quiet --target "$DIST" --no-deps "$HERE/.."

# 3) The Function Compute handler at the bundle root.
cp "$HERE/handler.py" "$DIST/handler.py"

echo "Built Linux/py${PYVER} deployment bundle at $DIST"
