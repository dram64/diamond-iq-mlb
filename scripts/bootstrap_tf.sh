#!/usr/bin/env bash
# One-time helper: terraform init/plan/apply for the state bootstrap.
# Prompts for confirmation before apply and prints the backend config on success.
#
# Usage:
#   AWS_PROFILE=diamond-iq scripts/bootstrap_tf.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BOOTSTRAP_DIR="${ROOT}/infrastructure/bootstrap"

if ! command -v terraform >/dev/null 2>&1; then
  echo "error: terraform not found on PATH" >&2
  exit 127
fi

if ! aws sts get-caller-identity >/dev/null 2>&1; then
  echo "error: AWS credentials not configured. Set AWS_PROFILE or run aws configure." >&2
  exit 1
fi

cd "${BOOTSTRAP_DIR}"

echo "==> terraform init"
terraform init -input=false

echo
echo "==> terraform plan"
terraform plan -out=tfplan -input=false

echo
read -r -p "Apply this plan? [y/N] " confirm
case "${confirm}" in
  y|Y|yes|YES) ;;
  *)
    echo "Aborted; tfplan kept for inspection."
    exit 0
    ;;
esac

echo
echo "==> terraform apply"
terraform apply -input=false tfplan
rm -f tfplan

echo
echo "==> Outputs"
terraform output

echo
echo "==> Backend config block (copy into infrastructure/main.tf):"
terraform output -raw backend_config_hcl
