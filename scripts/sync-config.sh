#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

ENVIRONMENT="dev"
DRY_RUN=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--env dev|stg|prod] [--dry-run]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

activate_scripts_venv
CONFIG_FILE="$(config_file_for "$ENVIRONMENT")"
python "$PROJECT_ROOT/scripts/config.py" --file "$CONFIG_FILE" validate
PROFILE="$(config_get "$CONFIG_FILE" aws_profile)"
REGION="$(config_get "$CONFIG_FILE" aws_region)"

if [[ "$DRY_RUN" == false ]]; then
  ensure_aws_session "$PROFILE" "$REGION"
fi

ARGS=(--config "$CONFIG_FILE")
if [[ "$DRY_RUN" == true ]]; then ARGS+=(--dry-run); fi
python "$PROJECT_ROOT/scripts/sync-config.py" "${ARGS[@]}"
