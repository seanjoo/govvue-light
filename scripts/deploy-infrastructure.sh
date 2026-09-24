#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

ENVIRONMENT="dev"
BUILD_ID="${BUILD_ID:-$(utc_build_id)}"
REUSE_LAMBDA=false
BOOTSTRAP_ONLY=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENVIRONMENT="$2"; shift 2 ;;
    --build-id) BUILD_ID="$2"; shift 2 ;;
    --reuse-lambda) REUSE_LAMBDA=true; shift ;;
    --bootstrap-only) BOOTSTRAP_ONLY=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--env dev|stg|prod] [--build-id ID] [--reuse-lambda] [--bootstrap-only]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

activate_scripts_venv
CONFIG_FILE="$(config_file_for "$ENVIRONMENT")"
python "$PROJECT_ROOT/scripts/config.py" --file "$CONFIG_FILE" validate
PROJECT_NAME="$(config_get "$CONFIG_FILE" project_name)"
PROFILE="$(config_get "$CONFIG_FILE" aws_profile)"
REGION="$(config_get "$CONFIG_FILE" aws_region)"
BOOTSTRAP_STACK="$PROJECT_NAME-$ENVIRONMENT-bootstrap"
APP_STACK="$PROJECT_NAME-$ENVIRONMENT"
SSM_PREFIX="/$PROJECT_NAME/$ENVIRONMENT"

ensure_aws_session "$PROFILE" "$REGION"
echo "Deploying bootstrap stack $BOOTSTRAP_STACK..."
aws cloudformation deploy \
  --template-file "$PROJECT_ROOT/infrastructure/bootstrap.yaml" \
  --stack-name "$BOOTSTRAP_STACK" \
  --parameter-overrides ProjectName="$PROJECT_NAME" Environment="$ENVIRONMENT" \
  --no-fail-on-empty-changeset \
  --profile "$PROFILE" --region "$REGION"

ARTIFACT_BUCKET="$(stack_output "$BOOTSTRAP_STACK" ArtifactBucketName "$PROFILE" "$REGION")"
if [[ -z "$ARTIFACT_BUCKET" || "$ARTIFACT_BUCKET" == "None" ]]; then
  echo "Artifact bucket output was not found." >&2
  exit 1
fi
echo "Artifact bucket: $ARTIFACT_BUCKET"

CFN_PREFIX="releases/$BUILD_ID/cloudformation"
aws s3 cp "$PROJECT_ROOT/infrastructure/bootstrap.yaml" "s3://$ARTIFACT_BUCKET/$CFN_PREFIX/bootstrap-$BUILD_ID.yaml" --sse AES256 --profile "$PROFILE" --region "$REGION" >/dev/null
aws s3 cp "$PROJECT_ROOT/infrastructure/app.yaml" "s3://$ARTIFACT_BUCKET/$CFN_PREFIX/app-$BUILD_ID.yaml" --sse AES256 --profile "$PROFILE" --region "$REGION" >/dev/null

if [[ "$BOOTSTRAP_ONLY" == true ]]; then
  echo "Bootstrap complete."
  exit 0
fi

if [[ "$REUSE_LAMBDA" == true ]]; then
  LAMBDA_KEY="$(stack_parameter "$APP_STACK" LambdaArtifactKey "$PROFILE" "$REGION")"
  LAMBDA_VERSION="$(stack_parameter "$APP_STACK" LambdaArtifactVersion "$PROFILE" "$REGION")"
  if [[ -z "$LAMBDA_KEY" || "$LAMBDA_KEY" == "None" ]]; then
    echo "No prior Lambda artifact exists. Run without --reuse-lambda for the initial deployment." >&2
    exit 1
  fi
  [[ "$LAMBDA_VERSION" == "None" ]] && LAMBDA_VERSION=""
  echo "Reusing Lambda artifact: s3://$ARTIFACT_BUCKET/$LAMBDA_KEY"
else
  LAMBDA_PACKAGE="$(BUILD_ID="$BUILD_ID" "$PROJECT_ROOT/scripts/build-lambda.sh" --build-id "$BUILD_ID")"
  LAMBDA_KEY="releases/$BUILD_ID/lambda/$(basename "$LAMBDA_PACKAGE")"
  LAMBDA_VERSION="$(aws s3api put-object \
    --bucket "$ARTIFACT_BUCKET" \
    --key "$LAMBDA_KEY" \
    --body "$LAMBDA_PACKAGE" \
    --content-type application/zip \
    --server-side-encryption AES256 \
    --query VersionId --output text \
    --profile "$PROFILE" --region "$REGION")"
  [[ "$LAMBDA_VERSION" == "None" ]] && LAMBDA_VERSION=""
  echo "Uploaded Lambda artifact: s3://$ARTIFACT_BUCKET/$LAMBDA_KEY (version $LAMBDA_VERSION)"
fi

echo "Deploying application stack $APP_STACK..."
aws cloudformation deploy \
  --template-file "$PROJECT_ROOT/infrastructure/app.yaml" \
  --stack-name "$APP_STACK" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
    ProjectName="$PROJECT_NAME" \
    Environment="$ENVIRONMENT" \
    ArtifactBucketName="$ARTIFACT_BUCKET" \
    LambdaArtifactKey="$LAMBDA_KEY" \
    LambdaArtifactVersion="$LAMBDA_VERSION" \
    BuildId="$BUILD_ID" \
    AppDomainName="$SSM_PREFIX/AppDomainName" \
    HostedZoneId="$SSM_PREFIX/HostedZoneId" \
    AcmCertificateArn="$SSM_PREFIX/AcmCertificateArn" \
    CognitoDomainName="$SSM_PREFIX/CognitoDomainName" \
    CognitoCertificateArn="$SSM_PREFIX/CognitoCertificateArn" \
    DailyFeedScheduleExpression="$SSM_PREFIX/DailyFeedScheduleExpression" \
    DailyFeedScheduleTimezone="$SSM_PREFIX/DailyFeedTimezone" \
    NotificationFromEmail="$SSM_PREFIX/NotificationFromEmail" \
    SesIdentityDomain="$SSM_PREFIX/SesIdentityDomain" \
  --no-fail-on-empty-changeset \
  --profile "$PROFILE" --region "$REGION"

MANIFEST_DIR="$PROJECT_ROOT/.build/$BUILD_ID"
mkdir -p "$MANIFEST_DIR"
jq -n \
  --arg buildId "$BUILD_ID" \
  --arg stackName "$APP_STACK" \
  --arg artifactBucket "$ARTIFACT_BUCKET" \
  --arg lambdaKey "$LAMBDA_KEY" \
  --arg lambdaVersion "$LAMBDA_VERSION" \
  '{buildId:$buildId,stackName:$stackName,artifactBucket:$artifactBucket,lambda:{key:$lambdaKey,versionId:$lambdaVersion}}' \
  > "$MANIFEST_DIR/infrastructure-manifest.json"

echo "Infrastructure deployment complete."
