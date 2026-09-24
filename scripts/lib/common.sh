#!/usr/bin/env bash
set -euo pipefail

SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_LIB_DIR/../.." && pwd)"
SCRIPTS_VENV="$PROJECT_ROOT/.venv"

activate_scripts_venv() {
  if [[ ! -d "$SCRIPTS_VENV" ]]; then
    python3 -m venv "$SCRIPTS_VENV"
  fi
  # shellcheck disable=SC1091
  source "$SCRIPTS_VENV/bin/activate"
  local marker="$SCRIPTS_VENV/.requirements.sha256"
  local required_hash
  required_hash="$(shasum -a 256 "$PROJECT_ROOT/scripts/requirements.txt" | awk '{print $1}')"
  if [[ ! -f "$marker" ]] || [[ "$(<"$marker")" != "$required_hash" ]]; then
    python -m pip install --quiet --upgrade pip
    python -m pip install --quiet -r "$PROJECT_ROOT/scripts/requirements.txt"
    printf '%s' "$required_hash" > "$marker"
  fi
}

config_file_for() {
  local environment="$1"
  printf '%s/config/%s.govvue-light.yml' "$PROJECT_ROOT" "$environment"
}

config_get() {
  local config_file="$1"
  local key="$2"
  python "$PROJECT_ROOT/scripts/config.py" --file "$config_file" get "$key"
}

ensure_aws_session() {
  local profile="$1"
  local region="$2"
  if ! aws sts get-caller-identity --profile "$profile" --region "$region" >/dev/null 2>&1; then
    echo "AWS session is not active for profile $profile; starting SSO login."
    aws sso login --profile "$profile"
  fi
}

stack_output() {
  local stack_name="$1"
  local output_key="$2"
  local profile="$3"
  local region="$4"
  aws cloudformation describe-stacks \
    --stack-name "$stack_name" \
    --query "Stacks[0].Outputs[?OutputKey=='${output_key}'].OutputValue | [0]" \
    --output text --profile "$profile" --region "$region"
}

stack_parameter() {
  local stack_name="$1"
  local parameter_key="$2"
  local profile="$3"
  local region="$4"
  aws cloudformation describe-stacks \
    --stack-name "$stack_name" \
    --query "Stacks[0].Parameters[?ParameterKey=='${parameter_key}'].ParameterValue | [0]" \
    --output text --profile "$profile" --region "$region" 2>/dev/null || true
}

utc_build_id() {
  date -u '+%Y%m%dT%H%M%SZ'
}
