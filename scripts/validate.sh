#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

ENVIRONMENT="dev"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 [--env dev|stg|prod]"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

activate_scripts_venv
CONFIG_FILE="$(config_file_for "$ENVIRONMENT")"
python "$PROJECT_ROOT/scripts/config.py" --file "$CONFIG_FILE" validate

echo "Checking shell scripts..."
for script in "$PROJECT_ROOT"/scripts/*.sh "$PROJECT_ROOT"/scripts/lib/*.sh; do
  bash -n "$script"
done

echo "Compiling and testing backend..."
python -m compileall -q "$PROJECT_ROOT/backend/src" "$PROJECT_ROOT/backend/tests"
python -m unittest discover -s "$PROJECT_ROOT/backend/tests" -p 'test_*.py'

echo "Linting CloudFormation..."
cfn-lint "$PROJECT_ROOT/infrastructure/bootstrap.yaml" "$PROJECT_ROOT/infrastructure/app.yaml"

echo "Auditing and building frontend..."
(
  cd "$PROJECT_ROOT/frontend"
  npm ci
  npm audit --audit-level=high
  npm run build
)

echo "All local validation passed."
