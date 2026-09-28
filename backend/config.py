# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
Amazon Connect Health Demo — Backend Configuration

All configurable values live here. Override via environment variables for deployment.
For local development, set values in your shell or a .env file.
"""
import os

# =============================================================================
# AWS Configuration
# =============================================================================
# In ECS, leave AWS_PROFILE empty to use IAM role.
# For local dev, set to your AWS CLI profile name.
AWS_PROFILE = os.environ.get("AWS_PROFILE", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

# =============================================================================
# Amazon Connect Health API (HealthAgent)
# =============================================================================
SERVICE_NAME = os.environ.get("SERVICE_NAME", "connecthealth")
# No "runtime." prefix here: StartPatientInsightsJob/GetPatientInsightsJob declare a
# hostPrefix="runtime." trait in the connecthealth service model, which botocore
# prepends automatically. Including it here too produces a broken double-prefixed
# host ("runtime.runtime.health-agent...") that fails DNS resolution.
SERVICE_ENDPOINT = os.environ.get("SERVICE_ENDPOINT", "https://health-agent.us-east-1.api.aws")
DOMAIN_ID = os.environ.get("DOMAIN_ID", "")  # e.g., dom-abc123def456

# =============================================================================
# HealthLake
# =============================================================================
HEALTHLAKE_DATASTORE_ID = os.environ.get("HEALTHLAKE_DATASTORE_ID", "")
HEALTHLAKE_DATASTORE_NAME = os.environ.get("HEALTHLAKE_DATASTORE_NAME", "")

# =============================================================================
# S3 - Patient Insights Output
# =============================================================================
S3_OUTPUT_BUCKET = os.environ.get("S3_OUTPUT_BUCKET", "")  # e.g., s3://my-bucket/insights-output/

# =============================================================================
# S3 - Streaming Output
# =============================================================================
STREAMING_OUTPUT_BUCKET = os.environ.get("STREAMING_OUTPUT_BUCKET", "")  # e.g., my-bucket (no s3:// prefix)
STREAMING_OUTPUT_REGION = os.environ.get("STREAMING_OUTPUT_REGION", "us-east-1")

# =============================================================================
# SMS Configuration (optional — requires Pinpoint SMS setup)
# =============================================================================
SMS_AWS_PROFILE = os.environ.get("SMS_AWS_PROFILE", "")
SMS_REGION = os.environ.get("SMS_REGION", "us-east-1")
SMS_ORIGINATION_NUMBER = os.environ.get("SMS_ORIGINATION_NUMBER", "")  # e.g., +18005551234

# =============================================================================
# Bedrock - Narrative Synthesis
# =============================================================================
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")
BEDROCK_MAX_TOKENS = int(os.environ.get("BEDROCK_MAX_TOKENS", "2048"))

# =============================================================================
# Medical Coding fallback — Comprehend Medical (ICD-10) + Bedrock (CPT/E&M)
# =============================================================================
# Used when health-agent:GenerateMedicalCodes 500s/denies (it's a gated preview
# feature -- see CLAUDE.md). COMPREHEND_MEDICAL_MIN_SCORE follows AWS's own
# confidence-filtering guidance for feeding Comprehend Medical results to an LLM:
# https://docs.aws.amazon.com/prescriptive-guidance/latest/generative-ai-nlp-healthcare/comprehend-medical-rag.html
COMPREHEND_MEDICAL_REGION = os.environ.get("COMPREHEND_MEDICAL_REGION", "us-east-1")
COMPREHEND_MEDICAL_MIN_SCORE = float(os.environ.get("COMPREHEND_MEDICAL_MIN_SCORE", "0.4"))
# ICD-10 codes below this score are dropped entirely (not shown anywhere in the
# UI, not just demoted) -- kept separate from COMPREHEND_MEDICAL_MIN_SCORE above
# so tightening ICD-10 doesn't also shrink what's fed to Bedrock for CPT/E&M.
COMPREHEND_MEDICAL_ICD10_MIN_SCORE = float(os.environ.get("COMPREHEND_MEDICAL_ICD10_MIN_SCORE", "0.5"))

# Which provider POST /api/medical-codes uses:
#   auto                      (default) try GenerateMedicalCodes first, fall back
#                              to Comprehend Medical + Bedrock only if it fails.
#   connect-health             GenerateMedicalCodes only -- surfaces its real error
#                              instead of masking it with a fallback (useful for
#                              confirming whether gated access has been granted).
#   comprehend-medical-bedrock Skip GenerateMedicalCodes entirely and always use
#                              the fallback pipeline (useful once you know
#                              GenerateMedicalCodes is unavailable, or to iterate
#                              on the fallback's prompt without a wasted call).
# Set via `-c medicalCodesProvider=...` at deploy time (see cdk.json/README.md) or
# the MEDICAL_CODES_PROVIDER env var directly for local dev.
MEDICAL_CODES_PROVIDER = os.environ.get("MEDICAL_CODES_PROVIDER", "auto").strip().lower()
if MEDICAL_CODES_PROVIDER not in ("auto", "connect-health", "comprehend-medical-bedrock"):
    print(f"[config] Unrecognized MEDICAL_CODES_PROVIDER={MEDICAL_CODES_PROVIDER!r}, defaulting to 'auto'")
    MEDICAL_CODES_PROVIDER = "auto"

# =============================================================================
# Demo Mode - Cached S3 paths (patient_id -> s3_uri)
# After running Patient Insights jobs, add the output S3 URIs here to skip
# re-running jobs on every page load. Format:
#   "patient_fhir_id": "s3://bucket/insights-output/job-id/patient-id/summary.json"
# =============================================================================
DEMO_CACHE = {
    # Patient A
    "46383dd73c1d282831d3e7c9101d4901497c32345d4e2fcc657c2eaf9d03830d": os.environ.get("DEMO_CACHE_PATIENT_A", ""),
    # Patient B
    "698345153023e19306b525ad8a6c7eca0cfc22dfff2a21b51945d5175d6d18f2": os.environ.get("DEMO_CACHE_PATIENT_B", ""),
    # Patient C
    "0725e4075c0a604253ba23c24746cc8dea085e10cc6e9a51c309619a1d65137a": os.environ.get("DEMO_CACHE_PATIENT_C", ""),
}
# Remove empty entries
DEMO_CACHE = {k: v for k, v in DEMO_CACHE.items() if v}

# =============================================================================
# Server
# =============================================================================
SERVER_HOST = os.environ.get("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("SERVER_PORT", "5000"))
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# CORS - Allow frontend to call backend
# Add your CloudFront distribution URLs here after deployment.
CORS_ORIGINS = [
    "http://localhost:5000",
    "http://localhost:8000",
    "http://127.0.0.1:5000",
    "http://127.0.0.1:8000",
]
_extra_cors = os.environ.get("CORS_ORIGINS", "")
if _extra_cors:
    if _extra_cors.strip() == "*":
        CORS_ORIGINS = "*"
    else:
        CORS_ORIGINS.extend([u.strip() for u in _extra_cors.split(",") if u.strip()])

# =============================================================================
# Default Patient ID (from HealthLake)
# =============================================================================
DEFAULT_PATIENT_ID = os.environ.get("DEFAULT_PATIENT_ID", "")
