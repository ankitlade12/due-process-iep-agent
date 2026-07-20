#!/usr/bin/env bash
# Build a Linux CPython 3.10 bundle for Alibaba Function Compute.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$DEPLOY_DIR/.." && pwd)"
DIST_DIR="$DEPLOY_DIR/dist"
BUILD_DIR="$DEPLOY_DIR/dist.building"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

python3 -m pip install --quiet --target "$BUILD_DIR" \
  --ignore-installed \
  --platform manylinux2014_x86_64 \
  --python-version 3.10 --implementation cp --abi cp310 \
  --only-binary=:all: \
  openai exceptiongroup

python3 -m pip install --quiet --target "$BUILD_DIR" \
  --no-deps --upgrade "$REPO_DIR"

cp "$DEPLOY_DIR/handler.py" "$BUILD_DIR/handler.py"
rm -rf "$DIST_DIR"
mv "$BUILD_DIR" "$DIST_DIR"

echo "Built Function Compute bundle at $DIST_DIR"
