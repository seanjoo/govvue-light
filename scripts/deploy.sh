#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

ENVIRONMENT="dev"
COMPONENT="all"
BUILD_ID="${BUILD_ID:-$(utc_build_id)}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --component) COMPONENT="$2"; shift 2 ;;
    --build-id) BUILD_ID="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 [--env dev|stg|prod] [--component all|config|backend|infra|frontend] [--build-id ID]"
      echo "  all       Sync config, deploy backend/infra, and publish frontend"
      echo "  config    Synchronize YAML to SSM only"
      echo "  backend   Sync config, build a new Lambda release, and update the app stack"
      echo "  infra     Sync config and update CloudFormation while reusing the current Lambda ZIP"
      echo "  frontend  Build and publish only the frontend"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

case "$COMPONENT" in
  all)
    "$PROJECT_ROOT/scripts/sync-config.sh" --env "$ENVIRONMENT"
    BUILD_ID="$BUILD_ID" "$PROJECT_ROOT/scripts/deploy-infrastructure.sh" --env "$ENVIRONMENT" --build-id "$BUILD_ID"
    BUILD_ID="$BUILD_ID" "$PROJECT_ROOT/scripts/deploy-frontend.sh" --env "$ENVIRONMENT" --build-id "$BUILD_ID"
    ;;
  config)
    "$PROJECT_ROOT/scripts/sync-config.sh" --env "$ENVIRONMENT"
    ;;
  backend)
    "$PROJECT_ROOT/scripts/sync-config.sh" --env "$ENVIRONMENT"
    BUILD_ID="$BUILD_ID" "$PROJECT_ROOT/scripts/deploy-infrastructure.sh" --env "$ENVIRONMENT" --build-id "$BUILD_ID"
    ;;
  infra)
    "$PROJECT_ROOT/scripts/sync-config.sh" --env "$ENVIRONMENT"
    BUILD_ID="$BUILD_ID" "$PROJECT_ROOT/scripts/deploy-infrastructure.sh" --env "$ENVIRONMENT" --build-id "$BUILD_ID" --reuse-lambda
    ;;
  frontend)
    BUILD_ID="$BUILD_ID" "$PROJECT_ROOT/scripts/deploy-frontend.sh" --env "$ENVIRONMENT" --build-id "$BUILD_ID"
    ;;
  *) echo "Invalid component: $COMPONENT" >&2; exit 1 ;;
esac

echo "GovVue Light deployment finished with build ID $BUILD_ID."
