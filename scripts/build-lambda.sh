#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

BUILD_ID="${BUILD_ID:-$(utc_build_id)}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-id) BUILD_ID="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 [--build-id YYYYMMDDTHHMMSSZ]"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ ! "$BUILD_ID" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "Invalid build ID: $BUILD_ID" >&2
  exit 1
fi

activate_scripts_venv
echo "Running backend tests..." >&2
python -m unittest discover -s "$PROJECT_ROOT/backend/tests" -p 'test_*.py' >&2

BUILD_DIR="$PROJECT_ROOT/.build/$BUILD_ID/lambda"
PACKAGE_PATH="$BUILD_DIR/govvue-light-api-$BUILD_ID.zip"
mkdir -p "$BUILD_DIR/package"
cp "$PROJECT_ROOT"/backend/src/*.py "$BUILD_DIR/package/"
find "$BUILD_DIR/package" -type d -name __pycache__ -prune -exec rm -r {} +
(
  cd "$BUILD_DIR/package"
  zip -X -q -r "$PACKAGE_PATH" .
)
echo "Built Lambda package: $PACKAGE_PATH" >&2
printf '%s\n' "$PACKAGE_PATH"
