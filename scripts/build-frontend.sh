#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

BUILD_ID="${BUILD_ID:-$(utc_build_id)}"
API_BASE_URL=""
AWS_REGION=""
USER_POOL_ID=""
USER_POOL_CLIENT_ID=""
COGNITO_DOMAIN=""
APP_TITLE="GovVue Light"
DAILY_NOTIFICATION_DEFAULT_TIME="06:15"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-id) BUILD_ID="$2"; shift 2 ;;
    --api-base-url) API_BASE_URL="$2"; shift 2 ;;
    --aws-region) AWS_REGION="$2"; shift 2 ;;
    --user-pool-id) USER_POOL_ID="$2"; shift 2 ;;
    --user-pool-client-id) USER_POOL_CLIENT_ID="$2"; shift 2 ;;
    --cognito-domain) COGNITO_DOMAIN="$2"; shift 2 ;;
    --app-title) APP_TITLE="$2"; shift 2 ;;
    --daily-notification-default-time) DAILY_NOTIFICATION_DEFAULT_TIME="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 --api-base-url URL --aws-region REGION --user-pool-id ID --user-pool-client-id ID --cognito-domain URL [--app-title TITLE] [--daily-notification-default-time HH:MM] [--build-id ID]"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

for required in API_BASE_URL AWS_REGION USER_POOL_ID USER_POOL_CLIENT_ID COGNITO_DOMAIN; do
  if [[ -z "${!required}" ]]; then echo "$required is required" >&2; exit 1; fi
done

echo "Installing locked frontend dependencies..." >&2
(
  cd "$PROJECT_ROOT/frontend"
  npm ci
  npm run build
) >&2

python3 "$PROJECT_ROOT/scripts/render-runtime-config.py" \
  --output "$PROJECT_ROOT/frontend/dist/runtime-config.js" \
  --api-base-url "$API_BASE_URL" \
  --aws-region "$AWS_REGION" \
  --user-pool-id "$USER_POOL_ID" \
  --user-pool-client-id "$USER_POOL_CLIENT_ID" \
  --cognito-domain "$COGNITO_DOMAIN" \
  --app-title "$APP_TITLE" \
  --daily-notification-default-time "$DAILY_NOTIFICATION_DEFAULT_TIME" \
  --build-id "$BUILD_ID"

BUILD_DIR="$PROJECT_ROOT/.build/$BUILD_ID/frontend"
PACKAGE_PATH="$BUILD_DIR/govvue-light-frontend-$BUILD_ID.zip"
mkdir -p "$BUILD_DIR"
(
  cd "$PROJECT_ROOT/frontend/dist"
  zip -X -q -r "$PACKAGE_PATH" .
)
echo "Built frontend package: $PACKAGE_PATH" >&2
printf '%s\n' "$PACKAGE_PATH"
