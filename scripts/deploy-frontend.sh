#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

ENVIRONMENT="dev"
BUILD_ID="${BUILD_ID:-$(utc_build_id)}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --build-id) BUILD_ID="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 [--env dev|stg|prod] [--build-id ID]"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

activate_scripts_venv
CONFIG_FILE="$(config_file_for "$ENVIRONMENT")"
python "$PROJECT_ROOT/scripts/config.py" --file "$CONFIG_FILE" validate
PROJECT_NAME="$(config_get "$CONFIG_FILE" project_name)"
PROFILE="$(config_get "$CONFIG_FILE" aws_profile)"
REGION="$(config_get "$CONFIG_FILE" aws_region)"
APP_STACK="$PROJECT_NAME-$ENVIRONMENT"
ensure_aws_session "$PROFILE" "$REGION"

API_BASE_URL="$(stack_output "$APP_STACK" ApiEndpoint "$PROFILE" "$REGION")"
USER_POOL_ID="$(stack_output "$APP_STACK" CognitoUserPoolId "$PROFILE" "$REGION")"
USER_POOL_CLIENT_ID="$(stack_output "$APP_STACK" CognitoClientId "$PROFILE" "$REGION")"
WEBSITE_BUCKET="$(stack_output "$APP_STACK" WebsiteBucketName "$PROFILE" "$REGION")"
DISTRIBUTION_ID="$(stack_output "$APP_STACK" CloudFrontDistributionId "$PROFILE" "$REGION")"
ARTIFACT_BUCKET="$(stack_output "$APP_STACK" ArtifactBucketName "$PROFILE" "$REGION")"
APP_TITLE="$(aws ssm get-parameter \
  --name "/$PROJECT_NAME/$ENVIRONMENT/FrontendTitle" \
  --query Parameter.Value --output text \
  --profile "$PROFILE" --region "$REGION")"
DAILY_NOTIFICATION_DEFAULT_TIME="$(aws ssm get-parameter \
  --name "/$PROJECT_NAME/$ENVIRONMENT/DailyNotificationDefaultTime" \
  --query Parameter.Value --output text \
  --profile "$PROFILE" --region "$REGION")"

FRONTEND_PACKAGE="$(BUILD_ID="$BUILD_ID" "$PROJECT_ROOT/scripts/build-frontend.sh" \
  --build-id "$BUILD_ID" \
  --api-base-url "$API_BASE_URL" \
  --aws-region "$REGION" \
  --user-pool-id "$USER_POOL_ID" \
  --user-pool-client-id "$USER_POOL_CLIENT_ID" \
  --app-title "$APP_TITLE" \
  --daily-notification-default-time "$DAILY_NOTIFICATION_DEFAULT_TIME")"

FRONTEND_KEY="releases/$BUILD_ID/frontend/$(basename "$FRONTEND_PACKAGE")"
FRONTEND_VERSION="$(aws s3api put-object \
  --bucket "$ARTIFACT_BUCKET" \
  --key "$FRONTEND_KEY" \
  --body "$FRONTEND_PACKAGE" \
  --content-type application/zip \
  --server-side-encryption AES256 \
  --query VersionId --output text \
  --profile "$PROFILE" --region "$REGION")"

echo "Publishing frontend to s3://$WEBSITE_BUCKET..."
aws s3 sync "$PROJECT_ROOT/frontend/dist/" "s3://$WEBSITE_BUCKET/" \
  --delete \
  --exclude index.html \
  --exclude runtime-config.js \
  --cache-control 'public,max-age=31536000,immutable' \
  --profile "$PROFILE" --region "$REGION"
aws s3 cp "$PROJECT_ROOT/frontend/dist/index.html" "s3://$WEBSITE_BUCKET/index.html" \
  --content-type text/html \
  --cache-control 'no-cache,no-store,must-revalidate' \
  --profile "$PROFILE" --region "$REGION"
aws s3 cp "$PROJECT_ROOT/frontend/dist/runtime-config.js" "s3://$WEBSITE_BUCKET/runtime-config.js" \
  --content-type application/javascript \
  --cache-control 'no-cache,no-store,must-revalidate' \
  --profile "$PROFILE" --region "$REGION"

aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths '/*' \
  --profile "$PROFILE" >/dev/null

MANIFEST_DIR="$PROJECT_ROOT/.build/$BUILD_ID"
mkdir -p "$MANIFEST_DIR"
jq -n \
  --arg buildId "$BUILD_ID" \
  --arg key "$FRONTEND_KEY" \
  --arg versionId "$FRONTEND_VERSION" \
  --arg websiteBucket "$WEBSITE_BUCKET" \
  '{buildId:$buildId,frontend:{key:$key,versionId:$versionId},websiteBucket:$websiteBucket}' \
  > "$MANIFEST_DIR/frontend-manifest.json"

echo "Frontend deployment complete: $(stack_output "$APP_STACK" WebsiteUrl "$PROFILE" "$REGION")"
