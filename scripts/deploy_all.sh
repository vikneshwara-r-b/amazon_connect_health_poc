#!/usr/bin/env bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# Master deploy script: `cdk deploy "*"` followed by loading the 3 sample FHIR
# patients into the newly-deployed HealthLake datastore. This automates exactly
# the two manual steps documented in README.md's "Deploy" and "After deployment:
# load sample FHIR data into HealthLake" sections -- it doesn't do anything those
# steps don't already do individually.
#
# Usage:
#   scripts/deploy_all.sh --profile <aws-profile> --password <cognito-demo-password> [options]
#
# Required:
#   --profile PROFILE     AWS CLI profile to deploy with
#   --password PASSWORD   Cognito demo user password (passed as -c demoUserPassword;
#                          never written to cdk.json -- see README.md's Security notes)
#
# Optional:
#   --region REGION        AWS region (default: us-east-1)
#   --vpc-id VPC_ID        Pass -c vpcId=<vpc-id> -- required for accounts with no
#                          default VPC (e.g. data_sandbox_cdk; see CLAUDE.md)
#   --environment ENV      cdk.json "environment" context value (default: dev) --
#                          also the SSM path segment used to look up the deployed
#                          HealthLake datastore ID afterward
#   --bootstrap            Run `cdk bootstrap` first (only needed once per account/region)
#   --yes                  Pass --require-approval never to `cdk deploy`, skipping the
#                          interactive confirmation prompt for IAM/security-group
#                          changes. Only use this for a run you don't intend to watch.
#   --skip-data-load       Deploy only; don't load sample FHIR data afterward
#   -h, --help             Show this help
#
# Example:
#   scripts/deploy_all.sh --profile data_sandbox_cdk --password 'Str0ng!Pass' \
#     --vpc-id vpc-0faafde279d3be756
#
# Safe to re-run for redeploying code changes -- `cdk deploy` only updates what
# changed. NOT safe to re-run purely to reload sample data: the loader
# (scripts/load_sample_healthlake_data.py) writes Patients by fixed ID but creates
# fresh Conditions/Observations/Encounters/MedicationRequests each time, so running
# this script twice against the same datastore duplicates that clinical history.
# Use --skip-data-load on a second run, or scripts/purge_healthlake_data.py first.

set -euo pipefail

usage() {
    sed -n '/^# Usage:/,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d; s/^# \{0,1\}//'
    exit "${1:-0}"
}

PROFILE=""
PASSWORD=""
REGION="us-east-1"
VPC_ID=""
ENVIRONMENT="dev"
DO_BOOTSTRAP=false
APPROVAL_FLAG=""
SKIP_DATA_LOAD=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --profile) PROFILE="$2"; shift 2 ;;
        --password) PASSWORD="$2"; shift 2 ;;
        --region) REGION="$2"; shift 2 ;;
        --vpc-id) VPC_ID="$2"; shift 2 ;;
        --environment) ENVIRONMENT="$2"; shift 2 ;;
        --bootstrap) DO_BOOTSTRAP=true; shift ;;
        --yes) APPROVAL_FLAG="--require-approval never"; shift ;;
        --skip-data-load) SKIP_DATA_LOAD=true; shift ;;
        -h|--help) usage 0 ;;
        *) echo "Unknown option: $1" >&2; usage 1 ;;
    esac
done

if [[ -z "$PROFILE" ]]; then echo "Error: --profile is required" >&2; usage 1; fi
if [[ -z "$PASSWORD" ]]; then echo "Error: --password is required (Cognito demo user password)" >&2; usage 1; fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "==> Verifying AWS credentials for profile '$PROFILE'..."
aws sts get-caller-identity --profile "$PROFILE" --region "$REGION" >/dev/null

# Reuse the repo's own venv (already has aws-cdk-lib + boto3 + requests) if present;
# otherwise fall back to whatever python3 is on PATH.
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON="$REPO_ROOT/.venv/bin/python"
    # shellcheck disable=SC1091
    source "$REPO_ROOT/.venv/bin/activate"
else
    PYTHON="python3"
fi

CDK_CONTEXT_ARGS=(-c "environment=$ENVIRONMENT" -c "demoUserPassword=$PASSWORD")
if [[ -n "$VPC_ID" ]]; then
    CDK_CONTEXT_ARGS+=(-c "vpcId=$VPC_ID")
fi

if $DO_BOOTSTRAP; then
    echo "==> Running cdk bootstrap (one-time per account/region)..."
    cdk bootstrap --profile "$PROFILE" "${CDK_CONTEXT_ARGS[@]}"
fi

echo "==> Deploying all CDK stacks (cdk deploy \"*\")..."
# shellcheck disable=SC2086  # APPROVAL_FLAG is intentionally word-split when non-empty
cdk deploy --profile "$PROFILE" "${CDK_CONTEXT_ARGS[@]}" $APPROVAL_FLAG "*"

if $SKIP_DATA_LOAD; then
    echo "==> --skip-data-load given; not loading sample FHIR data."
else
    echo "==> Looking up the deployed HealthLake datastore ID from SSM..."
    DATASTORE_ID=$(aws ssm get-parameter \
        --name "/connect-health/${ENVIRONMENT}/healthlakeDatastoreId" \
        --profile "$PROFILE" --region "$REGION" \
        --query "Parameter.Value" --output text)
    echo "    datastore ID: $DATASTORE_ID"

    echo "==> Loading sample FHIR data (3 demo patients) into HealthLake..."
    "$PYTHON" scripts/load_sample_healthlake_data.py \
        --datastore-id "$DATASTORE_ID" --profile "$PROFILE" --region "$REGION"
fi

echo "==> Deploy complete. Frontend URL:"
aws cloudformation describe-stacks \
    --stack-name AmazonConnectHealthFrontend \
    --profile "$PROFILE" --region "$REGION" \
    --query "Stacks[0].Outputs[?OutputKey=='FrontendUrl'].OutputValue" --output text
