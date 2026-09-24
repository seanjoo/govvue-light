#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

ENVIRONMENT="dev"
EMAIL=""
ROLE="user"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --role) ROLE="$2"; shift 2 ;;
    -h|--help) echo "Usage: $0 --email you@example.com [--role user|admin] [--env dev|stg|prod]"; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done
if [[ -z "$EMAIL" ]]; then echo "--email is required" >&2; exit 1; fi
if [[ "$ROLE" != "user" && "$ROLE" != "admin" ]]; then echo "--role must be user or admin" >&2; exit 1; fi

activate_scripts_venv
CONFIG_FILE="$(config_file_for "$ENVIRONMENT")"
PROJECT_NAME="$(config_get "$CONFIG_FILE" project_name)"
PROFILE="$(config_get "$CONFIG_FILE" aws_profile)"
REGION="$(config_get "$CONFIG_FILE" aws_region)"
APP_STACK="$PROJECT_NAME-$ENVIRONMENT"
ensure_aws_session "$PROFILE" "$REGION"
USER_POOL_ID="$(stack_output "$APP_STACK" CognitoUserPoolId "$PROFILE" "$REGION")"

SES_STATUS="$(aws sesv2 get-email-identity \
  --email-identity "$EMAIL" \
  --query '[to_string(VerifiedForSendingStatus),VerificationStatus]' \
  --output text \
  --profile "$PROFILE" --region "$REGION" 2>/dev/null || true)"

if [[ "$SES_STATUS" == true* ]]; then
  echo "SES identity for $EMAIL is already verified."
elif [[ "$SES_STATUS" == *$'\tPENDING' || "$SES_STATUS" == *$'\tNOT_STARTED' ]]; then
  echo "SES verification for $EMAIL is already pending. The user must follow the verification link before daily notifications can be delivered while SES is sandboxed."
else
  if [[ -n "$SES_STATUS" && "$SES_STATUS" != "None" ]]; then
    aws sesv2 delete-email-identity \
      --email-identity "$EMAIL" \
      --profile "$PROFILE" --region "$REGION"
  fi
  aws sesv2 create-email-identity \
    --email-identity "$EMAIL" \
    --profile "$PROFILE" --region "$REGION" >/dev/null
  echo "Requested SES verification for $EMAIL. The user must follow the verification link before daily notifications can be delivered while SES is sandboxed."
fi

COGNITO_USERNAME="$(aws cognito-idp admin-create-user \
  --user-pool-id "$USER_POOL_ID" \
  --username "$EMAIL" \
  --user-attributes Name=email,Value="$EMAIL" Name=email_verified,Value=true \
  --desired-delivery-mediums EMAIL \
  --query 'User.Username' \
  --output text \
  --profile "$PROFILE" --region "$REGION")"

aws cognito-idp admin-add-user-to-group \
  --user-pool-id "$USER_POOL_ID" \
  --username "$COGNITO_USERNAME" \
  --group-name "$ROLE" \
  --profile "$PROFILE" --region "$REGION"

echo "Created $EMAIL with role $ROLE. Cognito generated a temporary password and sent the invitation by email."
