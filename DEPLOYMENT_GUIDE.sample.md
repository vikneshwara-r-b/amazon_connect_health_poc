# ConnectHealth Demo — Deployment Guide

This guide walks through deploying the full stack to AWS, then covers local development.

## Full Stack Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              BROWSER                                         │
└─────────────────────────────────────────────────────────────────────────────┘
                │                    │                      │
                ▼                    ▼                      ▼
┌───────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐
│  Frontend CloudFront  │  │  Backend CloudFront │  │  WebSocket CloudFront   │
│  (HTTPS - Static)     │  │  (HTTPS - API)      │  │  (WSS - Streaming)      │
└───────────────────────┘  └─────────────────────┘  └─────────────────────────┘
                │                    │                      │
                ▼                    ▼                      ▼
┌───────────────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐
│      S3 Bucket        │  │   Backend ALB       │  │   Streaming ALB         │
│  (HTML/JS/CSS)        │  │   (HTTP:80)         │  │   (HTTP:80)             │
└───────────────────────┘  └─────────────────────┘  └─────────────────────────┘
                                     │                      │
                                     ▼                      ▼
                           ┌─────────────────────┐  ┌─────────────────────────┐
                           │  ECS Fargate        │  │  ECS Fargate            │
                           │  (Python Flask)     │  │  (Java WebSocket)       │
                           └─────────────────────┘  └─────────────────────────┘
                                     │                      │
                    ┌────────────────┼──────────────────────┘
                    ▼                ▼
           ┌─────────────┐  ┌─────────────────┐  ┌─────────────────┐
           │ HealthLake  │  │ ConnectHealth    │  │  S3 Output      │
           │ (FHIR Data) │  │ (Streaming API)  │  │  (Clinical Notes)│
           └─────────────┘  └─────────────────┘  └─────────────────┘
```

## Prerequisites

- Java 17+ and Maven 3.6+
- Python 3.9+ and pip
- AWS CLI v2.34+ configured with appropriate credentials (run `aws --version` to check; [update instructions](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html))
- An Amazon HealthLake FHIR datastore with patient data loaded (see below)

> **Note:** These instructions use `us-east-1` throughout. Amazon Connect Health is also available in `us-west-2`. Replace the region in all commands and configuration if you are deploying to a different region.

### 1. Create a Connect Health Domain

A domain is a logical container for all Connect Health resources in your account. If you already have one, skip this step.

```bash
aws connecthealth create-domain \
  --name "connect-health-demo" \
  --profile <YOUR_AWS_PROFILE> --region us-east-1
```

Note the `domainId` from the response (e.g., `dom-abc123`). You'll need it for Steps 1c and 2c.

### 2. Create a Subscription (Required for Streaming)

A subscription enables the streaming (ambient documentation) capability for your domain.

```bash
aws connecthealth create-subscription \
  --domain-id <YOUR_DOMAIN_ID> \
  --profile <YOUR_AWS_PROFILE> --region us-east-1
```

Note the `subscriptionId` from the response (e.g., `sub-xyz789`). You'll need it for Step 2c.

### 3. HealthLake FHIR Data

The application reads patient data from an Amazon HealthLake FHIR R4 datastore. Without patient data loaded, the patient list will be empty and Patient Insights will have nothing to summarize.

**Create a datastore** (takes ~15 minutes to provision):
```bash
aws healthlake create-fhir-datastore \
  --datastore-name "connect-health-demo" \
  --datastore-type-version R4 \
  --profile <YOUR_AWS_PROFILE> --region us-east-1
```

Note the `DatastoreId` from the output. You'll need it for Step 1c.

**Load patient data** using the [HealthLake FHIR REST API](https://docs.aws.amazon.com/healthlake/latest/devguide/crud-healthlake.html) or the [bulk import API](https://docs.aws.amazon.com/healthlake/latest/devguide/import-datastore.html) for NDJSON files.

The datastore needs at minimum a `Patient` resource for each patient you want to display. For a richer Patient Insights experience, load additional resource types: `Condition`, `Observation`, `Encounter`, `MedicationRequest`, `Procedure`, `DiagnosticReport`, `DocumentReference`, and `Immunization`.

> **Note:** You can verify the deployment works before loading FHIR data by using the built-in demo mode (`Ctrl+Shift+D`), which uses cached API responses and requires no HealthLake data or live API calls.

## CloudFormation Stacks Overview

The deployment consists of 8 CloudFormation stacks:

| Stack | Template | Purpose |
|-------|----------|---------|
| `connect-health-cognito-dev` | `infrastructure/cognito-stack.yaml` | Cognito User Pool for authentication |
| `patient-insights-backend-codebuild-dev` | `backend/infrastructure/codebuild-stack.yaml` | ECR repo + CodeBuild for backend |
| `patient-insights-backend-dev` | `backend/infrastructure/cloudformation.yaml` | Backend ECS Fargate + ALB |
| `patient-insights-backend-cloudfront` | `backend/infrastructure/cloudfront-proxy-stack.yaml` | HTTPS proxy for backend ALB |
| `connect-health-streaming-codebuild-dev` | `streaming-service/infrastructure/codebuild-stack.yaml` | ECR repo + CodeBuild for streaming |
| `connect-health-streaming-dev` | `streaming-service/infrastructure/cloudformation.yaml` | Streaming ECS Fargate + ALB |
| `connect-health-websocket-proxy` | `streaming-service/infrastructure/cloudfront-wss-stack.yaml` | WSS proxy for streaming ALB |
| `connect-health-frontend-dev` | `streaming-service/infrastructure/cloudfront-stack.yaml` | S3 + CloudFront for frontend |

---

## Step 0: Deploy Cognito Authentication (Optional)

Cognito provides a login gate so only authorized users can access the application. If you skip this step, the app runs without authentication.

### 0a. Deploy Cognito Stack

```bash
aws cloudformation create-stack \
  --stack-name connect-health-cognito-dev \
  --template-body file://infrastructure/cognito-stack.yaml \
  --parameters \
    ParameterKey=Environment,ParameterValue=dev \
    ParameterKey=DemoUserEmail,ParameterValue=connecthealth_demo@example.com \
    ParameterKey=DemoUserPassword,ParameterValue=ConnectHealth_123 \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile <YOUR_AWS_PROFILE> --region us-east-1

aws cloudformation wait stack-create-complete \
  --stack-name connect-health-cognito-dev \
  --profile <YOUR_AWS_PROFILE>
```

### 0b. Get Cognito Outputs

```bash
USER_POOL_ID=$(aws cloudformation describe-stacks \
  --stack-name connect-health-cognito-dev \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

CLIENT_ID=$(aws cloudformation describe-stacks \
  --stack-name connect-health-cognito-dev \
  --query "Stacks[0].Outputs[?OutputKey=='UserPoolClientId'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

echo "User Pool ID: $USER_POOL_ID"
echo "Client ID: $CLIENT_ID"
```

### 0c. Create a Demo User

```bash
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username demo@example.com \
  --user-attributes Name=email,Value=demo@example.com Name=name,Value="Demo User" \
  --temporary-password "TempPass123" \
  --profile <YOUR_AWS_PROFILE> --region us-east-1
```

The user will be prompted to set a new password on first login.

### 0d. Update Frontend Config

In `frontend/js/config.js`, set the Cognito values:

```javascript
window.COGNITO_CONFIG = {
    userPoolId: 'us-east-1_XXXXXXXXX',  // from 0b
    clientId: 'xxxxxxxxxxxxxxxxxxxxxxxxxx',  // from 0b
    region: 'us-east-1'
};
```

### 0e. Pass Cognito to Backend Stack

When deploying the backend (Step 1c), add these parameters:

```bash
ParameterKey=CognitoUserPoolId,ParameterValue=$USER_POOL_ID \
ParameterKey=CognitoClientId,ParameterValue=$CLIENT_ID \
```

---

## Step 1: Deploy the Backend

The backend is a Python Flask API that serves patient data from HealthLake and runs Patient Insights jobs.

### 1a. Deploy Backend CodeBuild Stack

```bash
aws cloudformation create-stack \
  --stack-name patient-insights-backend-codebuild-dev \
  --template-body file://backend/infrastructure/codebuild-stack.yaml \
  --parameters ParameterKey=Environment,ParameterValue=dev \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile <YOUR_AWS_PROFILE> --region us-east-1

aws cloudformation wait stack-create-complete \
  --stack-name patient-insights-backend-codebuild-dev \
  --profile <YOUR_AWS_PROFILE>
```

### 1b. Build and Push Backend Docker Image

```bash
cd backend
zip -r source.zip server.py config.py auth.py demo_mode.py demo_cache/ \
  requirements.txt Dockerfile

aws s3 cp source.zip s3://patient-insights-backend-source-<ACCOUNT_ID>-dev/source.zip \
  --profile <YOUR_AWS_PROFILE>

aws codebuild start-build \
  --project-name patient-insights-backend-build-dev \
  --profile <YOUR_AWS_PROFILE>
```

### 1c. Deploy Backend ECS Stack

> **Note:** If you ran Step 1b from the `backend/` directory, return to the repo root first: `cd ..`

```bash
ECR_URI=$(aws cloudformation describe-stacks \
  --stack-name patient-insights-backend-codebuild-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ECRRepositoryURI'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

# Get the latest image tag (build number)
IMAGE_TAG=$(aws ecr describe-images \
  --repository-name patient-insights-backend-dev \
  --query "sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]" \
  --output text --profile <YOUR_AWS_PROFILE>)

VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" \
  --query "Vpcs[0].VpcId" --output text --profile <YOUR_AWS_PROFILE>)

SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" \
  --query "Subnets[*].[SubnetId, AvailabilityZone]" \
  --output text --profile <YOUR_AWS_PROFILE> | sort -k2 -u | awk '{print $1}' | paste -sd, -)

aws cloudformation create-stack \
  --stack-name patient-insights-backend-dev \
  --template-body file://backend/infrastructure/cloudformation.yaml \
  --parameters \
    ParameterKey=Environment,ParameterValue=dev \
    ParameterKey=VpcId,ParameterValue=$VPC_ID \
    ParameterKey=SubnetIds,ParameterValue=\"$SUBNET_IDS\" \
    ParameterKey=ECRRepositoryURI,ParameterValue=$ECR_URI:$IMAGE_TAG \
    ParameterKey=HealthLakeDatastoreId,ParameterValue=<YOUR_DATASTORE_ID> \
    ParameterKey=DomainId,ParameterValue=<YOUR_DOMAIN_ID> \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile <YOUR_AWS_PROFILE> --region us-east-1

aws cloudformation wait stack-create-complete \
  --stack-name patient-insights-backend-dev \
  --profile <YOUR_AWS_PROFILE>
```

### 1d. Deploy Backend CloudFront HTTPS Proxy

```bash
# Get the backend ALB DNS
ALB_DNS=$(aws cloudformation describe-stacks \
  --stack-name patient-insights-backend-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ALBEndpoint'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

aws cloudformation create-stack \
  --stack-name patient-insights-backend-cloudfront \
  --template-body file://backend/infrastructure/cloudfront-proxy-stack.yaml \
  --parameters ParameterKey=ALBDomainName,ParameterValue=$ALB_DNS \
  --profile <YOUR_AWS_PROFILE> --region us-east-1

aws cloudformation wait stack-create-complete \
  --stack-name patient-insights-backend-cloudfront \
  --profile <YOUR_AWS_PROFILE>
```

---

## Step 2: Deploy the Streaming Service

The streaming service is a Java WebSocket server that bridges browser audio to the ConnectHealth streaming API.

### 2a. Deploy Streaming CodeBuild Stack

```bash
aws cloudformation create-stack \
  --stack-name connect-health-streaming-codebuild-dev \
  --template-body file://streaming-service/infrastructure/codebuild-stack.yaml \
  --parameters ParameterKey=Environment,ParameterValue=dev \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile <YOUR_AWS_PROFILE> --region us-east-1

aws cloudformation wait stack-create-complete \
  --stack-name connect-health-streaming-codebuild-dev \
  --profile <YOUR_AWS_PROFILE>
```

### 2b. Build and Push Streaming Docker Image

```bash
cd streaming-service
zip -r source.zip src pom.xml Dockerfile buildspec.yml

aws s3 cp source.zip s3://connect-health-streaming-source-<ACCOUNT_ID>-dev/source.zip \
  --profile <YOUR_AWS_PROFILE>

aws codebuild start-build \
  --project-name connect-health-streaming-build-dev \
  --profile <YOUR_AWS_PROFILE>
```

### 2c. Deploy Streaming ECS Stack

> **Note:** If you ran Step 2b from the `streaming-service/` directory, return to the repo root first: `cd ..`

```bash
ECR_URI=$(aws cloudformation describe-stacks \
  --stack-name connect-health-streaming-codebuild-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ECRRepositoryURI'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

# Get the latest image tag (build number)
IMAGE_TAG=$(aws ecr describe-images \
  --repository-name connect-health-streaming-dev \
  --query "sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]" \
  --output text --profile <YOUR_AWS_PROFILE>)

# Get the output bucket name from the backend stack
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name patient-insights-backend-dev \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

aws cloudformation create-stack \
  --stack-name connect-health-streaming-dev \
  --template-body file://streaming-service/infrastructure/cloudformation.yaml \
  --parameters \
    ParameterKey=Environment,ParameterValue=dev \
    ParameterKey=VpcId,ParameterValue=$VPC_ID \
    ParameterKey=SubnetIds,ParameterValue=\"$SUBNET_IDS\" \
    ParameterKey=ECRRepositoryURI,ParameterValue=$ECR_URI:$IMAGE_TAG \
    ParameterKey=OutputBucket,ParameterValue=s3://$OUTPUT_BUCKET \
    ParameterKey=DomainId,ParameterValue=<YOUR_DOMAIN_ID> \
    ParameterKey=SubscriptionId,ParameterValue=<YOUR_SUBSCRIPTION_ID> \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile <YOUR_AWS_PROFILE> --region us-east-1

aws cloudformation wait stack-create-complete \
  --stack-name connect-health-streaming-dev \
  --profile <YOUR_AWS_PROFILE>
```

### 2d. Deploy WebSocket CloudFront Proxy (WSS)

```bash
# Get the streaming ALB DNS
STREAMING_ALB=$(aws cloudformation describe-stacks \
  --stack-name connect-health-streaming-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ALBDNSName'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

aws cloudformation create-stack \
  --stack-name connect-health-websocket-proxy \
  --template-body file://streaming-service/infrastructure/cloudfront-wss-stack.yaml \
  --parameters ParameterKey=ALBDomainName,ParameterValue=$STREAMING_ALB \
  --profile <YOUR_AWS_PROFILE> --region us-east-1

aws cloudformation wait stack-create-complete \
  --stack-name connect-health-websocket-proxy \
  --profile <YOUR_AWS_PROFILE>
```

---

## Step 3: Deploy the Frontend

### 3a. Create S3 + CloudFront for Frontend

> **Note:** This stack creates a new S3 bucket for hosting the frontend static files. Choose a globally unique bucket name (e.g., `connect-health-frontend-<ACCOUNT_ID>`). Unlike the output buckets created automatically by the backend stack, this bucket must be explicitly named.

```bash
aws cloudformation create-stack \
  --stack-name connect-health-frontend-dev \
  --template-body file://streaming-service/infrastructure/cloudfront-stack.yaml \
  --parameters ParameterKey=FrontendBucketName,ParameterValue=<YOUR_FRONTEND_BUCKET> \
  --profile <YOUR_AWS_PROFILE> --region us-east-1

aws cloudformation wait stack-create-complete \
  --stack-name connect-health-frontend-dev \
  --profile <YOUR_AWS_PROFILE>
```

### 3b. Update Frontend Config

Get the CloudFront URLs from the stacks you just deployed:

```bash
BACKEND_CF=$(aws cloudformation describe-stacks \
  --stack-name patient-insights-backend-cloudfront \
  --query "Stacks[0].Outputs[?OutputKey=='BackendURL'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

WSS_CF=$(aws cloudformation describe-stacks \
  --stack-name connect-health-websocket-proxy \
  --query "Stacks[0].Outputs[?OutputKey=='WebSocketURL'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

echo "Backend CloudFront: $BACKEND_CF"
echo "WebSocket CloudFront: $WSS_CF"
```

Update `frontend/js/config.js` with these URLs. In the `configs` object, set the `deployed` block:

```javascript
deployed: {
    WS_URL: '<WSS_CF value from above>',
    BACKEND_URL: '<BACKEND_CF value from above>',
    ENV_NAME: 'deployed'
}
```

If you deployed Cognito (Step 0), also set the `COGNITO_CONFIG`:

```javascript
window.COGNITO_CONFIG = {
    userPoolId: '<USER_POOL_ID from Step 0b>',
    clientId: '<CLIENT_ID from Step 0b>',
    region: 'us-east-1'
};
```

### 3c. Upload Frontend to S3

```bash
aws s3 sync frontend s3://<YOUR_FRONTEND_BUCKET>/ \
  --exclude ".git/*" --exclude ".DS_Store" --profile <YOUR_AWS_PROFILE>

# Get the frontend CloudFront distribution ID
DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name connect-health-frontend-dev \
  --query "Stacks[0].Outputs[?OutputKey=='DistributionId'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

aws cloudfront create-invalidation \
  --distribution-id $DIST_ID --paths "/*" --profile <YOUR_AWS_PROFILE>
```

### 3d. Verify

Open the frontend CloudFront URL in your browser. You should see the EHR interface with patient data loading from HealthLake.

---

## Local Development

### Quick Start

```bash
# Terminal 1 — Backend (port 5000)
cd backend
AWS_PROFILE=<YOUR_AWS_PROFILE> python3 server.py

# Terminal 2 — Streaming Service (port 8081)
cd streaming-service
AWS_PROFILE=<YOUR_AWS_PROFILE> ./run.sh

# Browser
open http://localhost:5000
```

The `config.js` auto-detects `localhost` and routes API calls to local services.

| Environment | Backend URL | WebSocket URL |
|-------------|-------------|---------------|
| Local | `http://localhost:5000` | `ws://localhost:8081/stream` |
| Deployed | `https://<BACKEND_CF>.cloudfront.net` | `wss://<WSS_CF>.cloudfront.net/stream` |

---

## Updating Deployed Services

### Frontend

```bash
aws s3 sync frontend s3://<YOUR_FRONTEND_BUCKET>/ \
  --exclude ".git/*" --exclude ".DS_Store" --profile <YOUR_AWS_PROFILE>

aws cloudfront create-invalidation \
  --distribution-id <FRONTEND_DIST_ID> --paths "/*" --profile <YOUR_AWS_PROFILE>
```

### Backend

```bash
cd backend
zip -r source.zip server.py config.py auth.py demo_mode.py demo_cache/ \
  requirements.txt Dockerfile

aws s3 cp source.zip s3://patient-insights-backend-source-<ACCOUNT_ID>-dev/source.zip \
  --profile <YOUR_AWS_PROFILE>

aws codebuild start-build --project-name patient-insights-backend-build-dev \
  --profile <YOUR_AWS_PROFILE>

# After build completes, get the new image tag and update the stack:
IMAGE_TAG=$(aws ecr describe-images \
  --repository-name patient-insights-backend-dev \
  --query "sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]" \
  --output text --profile <YOUR_AWS_PROFILE>)

ECR_URI=$(aws cloudformation describe-stacks \
  --stack-name patient-insights-backend-codebuild-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ECRRepositoryURI'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

aws cloudformation update-stack \
  --stack-name patient-insights-backend-dev \
  --use-previous-template \
  --parameters \
    ParameterKey=ECRRepositoryURI,ParameterValue=$ECR_URI:$IMAGE_TAG \
    ParameterKey=Environment,UsePreviousValue=true \
    ParameterKey=VpcId,UsePreviousValue=true \
    ParameterKey=SubnetIds,UsePreviousValue=true \
    ParameterKey=HealthLakeDatastoreId,UsePreviousValue=true \
    ParameterKey=DomainId,UsePreviousValue=true \
    ParameterKey=CognitoUserPoolId,UsePreviousValue=true \
    ParameterKey=CognitoClientId,UsePreviousValue=true \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile <YOUR_AWS_PROFILE>
```

### Streaming Service

```bash
cd streaming-service
zip -r source.zip src pom.xml Dockerfile buildspec.yml

aws s3 cp source.zip s3://connect-health-streaming-source-<ACCOUNT_ID>-dev/source.zip \
  --profile <YOUR_AWS_PROFILE>

aws codebuild start-build --project-name connect-health-streaming-build-dev \
  --profile <YOUR_AWS_PROFILE>

# After build completes, get the new image tag and update the stack:
IMAGE_TAG=$(aws ecr describe-images \
  --repository-name connect-health-streaming-dev \
  --query "sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]" \
  --output text --profile <YOUR_AWS_PROFILE>)

ECR_URI=$(aws cloudformation describe-stacks \
  --stack-name connect-health-streaming-codebuild-dev \
  --query "Stacks[0].Outputs[?OutputKey=='ECRRepositoryURI'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)

aws cloudformation update-stack \
  --stack-name connect-health-streaming-dev \
  --use-previous-template \
  --parameters \
    ParameterKey=ECRRepositoryURI,ParameterValue=$ECR_URI:$IMAGE_TAG \
    ParameterKey=Environment,UsePreviousValue=true \
    ParameterKey=VpcId,UsePreviousValue=true \
    ParameterKey=SubnetIds,UsePreviousValue=true \
    ParameterKey=OutputBucket,UsePreviousValue=true \
    ParameterKey=DomainId,UsePreviousValue=true \
    ParameterKey=SubscriptionId,UsePreviousValue=true \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile <YOUR_AWS_PROFILE>
```

---

## Environment Variables

### Streaming Service (ECS Task)

> The ConnectHealth SDK auto-resolves endpoints based on region — no endpoint override needed.

| Variable | Value | Description |
|----------|-------|-------------|
| `CONNECT_HEALTH_REGION` | `us-east-1` | ConnectHealth API region |
| `OUTPUT_BUCKET` | `s3://<YOUR_BUCKET>` | S3 URI for streaming output (with `s3://` prefix) |
| `DOMAIN_ID` | `<YOUR_DOMAIN_ID>` | ConnectHealth domain ID |
| `SUBSCRIPTION_ID` | `<YOUR_SUBSCRIPTION_ID>` | ConnectHealth subscription ID |
| `PORT` | `8081` | WebSocket server port |

### Backend (ECS Task)

| Variable | Value | Description |
|----------|-------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region |
| `HEALTHLAKE_DATASTORE_ID` | `<YOUR_DATASTORE_ID>` | HealthLake FHIR datastore ID |
| `SERVICE_ENDPOINT` | `https://runtime.health-agent.us-east-1.api.aws` | ConnectHealth API |
| `DOMAIN_ID` | `<YOUR_DOMAIN_ID>` | ConnectHealth domain ID |
| `S3_OUTPUT_BUCKET` | `s3://<YOUR_BUCKET>/insights-output/` | S3 for Patient Insights output |
| `STREAMING_OUTPUT_BUCKET` | `<YOUR_BUCKET>` | S3 bucket for streaming output (no `s3://` prefix) |
| `SERVER_PORT` | `5000` | Backend server port |

### Caching Patient Insights Results (Optional)

By default, clicking a patient triggers a live `StartPatientInsightsJob` call, which takes 3–5 minutes to complete. For demos with static patient data, you can cache the output S3 path so subsequent clicks return results instantly.

1. Click a patient in the UI and wait for the Patient Insights job to complete
2. Note the S3 output path from the backend logs (or check S3 under `<YOUR_BUCKET>/insights-output/`)
3. Set the cache by either:
   - **Environment variable** (for ECS): Add to the backend task definition or CloudFormation parameters
   - **config.py** (for local dev): Edit the `DEMO_CACHE` dict in `backend/config.py`

The env var names map to patient FHIR IDs defined in `backend/config.py`:

```
DEMO_CACHE_PATIENT_A=s3://<YOUR_BUCKET>/insights-output/<JOB_ID>/<PATIENT_ID>/summary.json
DEMO_CACHE_PATIENT_B=s3://<YOUR_BUCKET>/insights-output/<JOB_ID>/<PATIENT_ID>/summary.json
DEMO_CACHE_PATIENT_C=s3://<YOUR_BUCKET>/insights-output/<JOB_ID>/<PATIENT_ID>/summary.json
```

These map to the three demo patients by their FHIR patient ID in `backend/config.py`. When set, the backend returns the cached S3 path immediately instead of starting a new job.

> **Note:** If the patient's HealthLake data changes (new encounters, lab results, medications), clear the cache to ensure the pre-visit summary reflects the latest data.

---

## IAM Permissions

### Streaming ECS Task Role

```json
{
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["health-agent:StartMedicalScribeListeningSession"],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::<YOUR_BUCKET>",
        "arn:aws:s3:::<YOUR_BUCKET>/*"
      ]
    }
  ]
}
```

### Backend ECS Task Role

- `healthlake:ReadResource`, `SearchWithGet`, `SearchWithPost`, `SearchEverything`, `GetCapabilities` — scoped to specific datastore ARN
- `health-agent:StartPatientInsightsJob`, `health-agent:GetPatientInsightsJob`, `health-agent:GenerateMedicalCodes` — ConnectHealth API (Patient Insights + Medical Coding)

> **Note:** Medical coding (GenerateMedicalCodes) is a gated preview feature. Contact your AWS account team to request access. The demo functions without it — ambient documentation and patient insights work independently.
- `s3:GetObject`, `s3:PutObject`, `s3:ListBucket` — for insights and streaming output buckets
- `bedrock:InvokeModel` — scoped to `us.anthropic.claude-sonnet-4-5-20250929-v1:0` for narrative synthesis

**Note:** The `S3OutputBucket` CloudFormation parameter takes just the bucket name (e.g., `my-bucket`). The template automatically constructs the full S3 URI (`s3://my-bucket/insights-output/`) for the `S3_OUTPUT_BUCKET` environment variable. Do not pass the `s3://` prefix or `/insights-output/` suffix in the parameter — the template adds them.

**Note:** The `healthlake:SearchEverything` permission is required by the Connect Health Patient Insights service to read patient data from HealthLake on your behalf. Without it, `StartPatientInsightsJob` will fail with `AccessDeniedException`.

---

## Security Notes

This is a demo application. The following design decisions prioritize ease of deployment and demo flexibility over production-hardened security:

- **CloudFront → ALB communication uses HTTP (port 80)**, not HTTPS. CloudFront terminates TLS from the browser, but the internal hop from CloudFront to the ALB is unencrypted. The ALB security groups restrict inbound traffic to the [CloudFront managed prefix list](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/LocationsOfEdgeServers.html), so only CloudFront can reach the ALBs. For production, add ACM certificates to the ALBs and configure CloudFront to use HTTPS origins.

- **CORS is configurable via CloudFormation parameter**. The backend CloudFormation template has a `CorsOrigin` parameter that defaults to `*` (wildcard) for development. For production, set this to your frontend CloudFront domain (e.g., `https://d1234abcd.cloudfront.net`).

- **Demo mode is toggled via a client-side header (`X-Demo-Mode`)**. When enabled (`Ctrl+Shift+D`), the frontend sends this header on API calls and the backend returns cached sample data instead of making live AWS calls. This was designed so the Service team can run demos without network connectivity or a deployed backend. The cached data is synthetic — no real PHI. Demo mode does not bypass Cognito authentication — all requests must still carry a valid JWT token. For production, remove the demo mode capability entirely or move it to a server-side environment variable.

### Production hardening recommendations

If you plan to adapt this demo for production use, address the following high-priority items identified during threat modeling:

| # | Area | Current demo state | Production recommendation |
|---|------|--------------------|---------------------------|
| 1 | **Unencrypted CloudFront → ALB traffic** — Patient FHIR data and clinical notes transit unencrypted between CloudFront and the ALB | ALB security groups restrict inbound to CloudFront managed prefix list only, limiting exposure | Add [ACM certificates](https://docs.aws.amazon.com/acm/latest/userguide/gs-acm-request-public.html) to both ALBs (backend and streaming). Configure CloudFront distributions to use [HTTPS-only origins](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-https-cloudfront-to-custom-origin.html) with TLS 1.2+. Redirect all HTTP listeners to HTTPS. |
| 2 | **Container image integrity** — Unverified container images in ECR could be modified to inject backdoors into backend or streaming services | ✅ ECR image scanning on push enabled. ✅ Immutable image tags enforced (`ImageTagMutability: IMMUTABLE`). Dockerfile uses non-root `USER appuser`. Container image signing not configured. | Implement container image signing with [AWS Signer](https://docs.aws.amazon.com/signer/latest/developerguide/Welcome.html). Restrict IAM policies for ECR push to the CI/CD pipeline only. |
| 3 | **S3 clinical output integrity** — Compromised S3 write permissions could allow tampering with SOAP notes and medical codes | ✅ S3 buckets encrypted at rest (AES-256). ✅ Public access blocked on all buckets. ✅ Deny non-HTTPS bucket policies applied. IAM task roles scoped to specific S3 actions on specific bucket ARNs. | Enable [S3 versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html) on all output buckets. Enable [MFA delete](https://docs.aws.amazon.com/AmazonS3/latest/userguide/MultiFactorAuthenticationDelete.html) to prevent unauthorized version removal. Consider [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html) (governance mode) for clinical outputs. |
| 4 | **Direct HealthLake access** — Compromised IAM credentials could bypass application-level access controls for bulk data extraction | IAM task roles scoped to specific HealthLake actions (`ReadResource`, `SearchWithGet`, etc.) on specific datastore ARN | Configure [VPC endpoints](https://docs.aws.amazon.com/healthlake/latest/devguide/vpc-endpoints.html) for HealthLake to restrict access to private network paths. Enable [CloudTrail data events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html) for HealthLake API calls and configure alerting for unusual access patterns. Apply [IAM condition keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_condition-keys.html) to restrict HealthLake access to specific VPC endpoints and ECS task roles. |
| 5 | **No WAF on CloudFront distributions** — No web application firewall to block common attack patterns | CloudFront distributions restrict viewer protocol to HTTPS-only with TLS 1.2+. ALBs are restricted to CloudFront-only traffic via managed prefix lists. | Add [AWS WAF](https://docs.aws.amazon.com/waf/latest/developerguide/waf-chapter.html) with AWS managed rule groups (AWSManagedRulesCommonRuleSet, AWSManagedRulesKnownBadInputsRuleSet) to all CloudFront distributions. |
| 6 | **No access logging on ALBs and CloudFront** — Limited visibility into traffic patterns and potential attacks | CloudWatch Container Insights enabled on ECS clusters. ECS task logs retained in CloudWatch. | Enable [ALB access logging](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/enable-access-logging.html) to S3. Enable [CloudFront access logging](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/AccessLogs.html). Configure log retention and alerting. |


---

## Troubleshooting

### Check ECS Logs
```bash
aws logs tail /ecs/connect-health-streaming-dev --since 10m --profile <YOUR_AWS_PROFILE>
aws logs tail /ecs/patient-insights-backend-dev --since 10m --profile <YOUR_AWS_PROFILE>
```

### Check ECS Task Status
```bash
aws ecs describe-services \
  --cluster connect-health-streaming-dev --services connect-health-streaming-dev \
  --profile <YOUR_AWS_PROFILE> \
  --query "services[0].{Running:runningCount,Desired:desiredCount}"
```

### Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| `BadRequestException: Validation failed` | Wrong region or missing domain/subscription ID | Check `CONNECT_HEALTH_REGION`, `DOMAIN_ID`, `SUBSCRIPTION_ID` |
| Streaming stack fails with "maximum number of rules per security group" | CloudFront prefix list has ~45 IPs, each counts as a rule | Default quota is 60 rules. Request increase to 120 via Service Quotas (L-0EA8095F) if adding port 443 rule |
| `AccessDeniedException: Service was not able to retrieve patient data` | Missing `healthlake:SearchEverything` IAM permission | Add `healthlake:SearchEverything` to the backend task role |
| Patient Insights returns 500 | `PermissionError` writing service model in Docker container | Ensure Dockerfile pre-installs the model before `USER appuser` |
| CORS errors in browser console | Frontend CloudFront domain not in CORS allowed origins | Set `CORS_ORIGINS=*` env var in backend ECS task (set by CloudFormation template) |
| WebSocket connection failed | Using `ws://` instead of `wss://` on CloudFront | Use the WSS CloudFront URL, not the ALB directly | <!-- nosemgrep: detect-insecure-websocket -->
| Patients don't load on CloudFront | Wrong HealthLake datastore ID in ECS env | Verify `HEALTHLAKE_DATASTORE_ID` in task definition |
| S3 validation errors | `S3OutputBucket` param includes `s3://` prefix | Pass just the bucket name — template adds `s3://` and `/insights-output/` |
| No transcription output | Wrong audio format | Must be 16kHz, 16-bit, mono PCM |
| Frontend shows stale content | CloudFront cache | Run invalidation, hard refresh (`Cmd+Shift+R`) |
| Login fails with "Unauthorized" | Cognito IDs not set in backend ECS env | Verify `COGNITO_USER_POOL_ID` and `COGNITO_CLIENT_ID` in task definition |
| Login screen doesn't appear | `COGNITO_CONFIG` has placeholder values in config.js | Update `userPoolId` and `clientId` in `frontend/js/config.js` with real values from Step 0b |
| Page reload shows login screen | Auth tokens not persisted | Update to latest `auth.js` which stores tokens in localStorage |

---

## Enabling Authentication

> If you already deployed Cognito in Step 0 and passed the Cognito parameters in Step 1c, skip to "Adding More Users" below.

If you initially deployed without authentication and want to add it later:

### Step 1: Update Backend Stack with Cognito Parameters

```bash
aws cloudformation update-stack \
  --stack-name patient-insights-backend-dev \
  --use-previous-template \
  --parameters \
    ParameterKey=Environment,UsePreviousValue=true \
    ParameterKey=VpcId,UsePreviousValue=true \
    ParameterKey=SubnetIds,UsePreviousValue=true \
    ParameterKey=ECRRepositoryURI,UsePreviousValue=true \
    ParameterKey=HealthLakeDatastoreId,UsePreviousValue=true \
    ParameterKey=ServiceEndpoint,UsePreviousValue=true \
    ParameterKey=DomainId,UsePreviousValue=true \
    ParameterKey=S3OutputBucket,UsePreviousValue=true \
    ParameterKey=StreamingOutputBucket,UsePreviousValue=true \
    ParameterKey=CognitoUserPoolId,ParameterValue=<USER_POOL_ID> \
    ParameterKey=CognitoClientId,ParameterValue=<CLIENT_ID> \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile <YOUR_AWS_PROFILE>
```

After the stack update completes, force a new ECS deployment to pick up the new env vars:

```bash
aws ecs update-service --cluster patient-insights-backend-dev \
  --service patient-insights-backend-dev --force-new-deployment \
  --profile <YOUR_AWS_PROFILE>
```

### Step 2: Update Frontend Config

In `frontend/js/config.js`, set the Cognito values:

```javascript
window.COGNITO_CONFIG = {
    userPoolId: '<USER_POOL_ID>',   // e.g., us-east-1_Twy2DNy5x
    clientId: '<CLIENT_ID>',         // e.g., 5b30r6frkj7f73ea1loonc9nhq
    region: 'us-east-1'
};
```

### Step 3: Redeploy Frontend

```bash
aws s3 sync frontend s3://<YOUR_FRONTEND_BUCKET>/ \
  --exclude ".git/*" --exclude ".DS_Store" --profile <YOUR_AWS_PROFILE>

aws cloudfront create-invalidation \
  --distribution-id <FRONTEND_DIST_ID> --paths "/*" --profile <YOUR_AWS_PROFILE>
```

### Step 4: Verify

Open the CloudFront URL. You should see a login screen. Sign in with the credentials you set when deploying the Cognito stack (Step 0).

### Disabling Authentication

To disable auth without tearing down the Cognito stack:
- Frontend: Set `userPoolId` and `clientId` back to `YOUR_COGNITO_USER_POOL_ID` / `YOUR_COGNITO_CLIENT_ID` (or empty strings) in `config.js`
- Backend: Set `CognitoUserPoolId` and `CognitoClientId` to empty strings in the CloudFormation stack update

### Adding More Users

```bash
USER_POOL_ID=<YOUR_USER_POOL_ID>

aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username newuser@example.com \
  --user-attributes Name=email,Value=newuser@example.com Name=email_verified,Value=true \
  --temporary-password "TempPass123" \
  --message-action SUPPRESS \
  --profile <YOUR_AWS_PROFILE> --region us-east-1

# Set permanent password (skips forced password change on first login)
aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username newuser@example.com \
  --password "PermanentPass123" \
  --permanent \
  --profile <YOUR_AWS_PROFILE> --region us-east-1
```

---

## Cleanup

Delete stacks in reverse order:

```bash
# Empty S3 buckets first (CloudFormation can't delete non-empty buckets)
FRONTEND_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name connect-health-frontend-dev \
  --query "Stacks[0].Parameters[?ParameterKey=='FrontendBucketName'].ParameterValue" \
  --output text --profile <YOUR_AWS_PROFILE>)
aws s3 rm s3://$FRONTEND_BUCKET --recursive --profile <YOUR_AWS_PROFILE>

# Empty the output bucket (Patient Insights results, streaming session files)
OUTPUT_BUCKET=$(aws cloudformation describe-stacks \
  --stack-name patient-insights-backend-dev \
  --query "Stacks[0].Outputs[?OutputKey=='OutputBucketName'].OutputValue" \
  --output text --profile <YOUR_AWS_PROFILE>)
aws s3 rm s3://$OUTPUT_BUCKET --recursive --profile <YOUR_AWS_PROFILE>

aws cloudformation delete-stack --stack-name connect-health-cognito-dev --profile <YOUR_AWS_PROFILE>
aws cloudformation delete-stack --stack-name connect-health-frontend-dev --profile <YOUR_AWS_PROFILE>
aws cloudformation delete-stack --stack-name connect-health-websocket-proxy --profile <YOUR_AWS_PROFILE>
aws cloudformation delete-stack --stack-name patient-insights-backend-cloudfront --profile <YOUR_AWS_PROFILE>

aws cloudformation delete-stack --stack-name connect-health-streaming-dev --profile <YOUR_AWS_PROFILE>
aws cloudformation wait stack-delete-complete --stack-name connect-health-streaming-dev --profile <YOUR_AWS_PROFILE>

aws cloudformation delete-stack --stack-name patient-insights-backend-dev --profile <YOUR_AWS_PROFILE>
aws cloudformation wait stack-delete-complete --stack-name patient-insights-backend-dev --profile <YOUR_AWS_PROFILE>

# Empty S3 buckets (versioned) and ECR repos are now handled automatically:
# - ECR repositories have EmptyOnDelete: true
# - S3 source buckets have a Lambda-backed custom resource that empties all object versions on stack deletion
# No manual cleanup needed — just delete the stacks:

aws cloudformation delete-stack --stack-name connect-health-streaming-codebuild-dev --profile <YOUR_AWS_PROFILE>
aws cloudformation delete-stack --stack-name patient-insights-backend-codebuild-dev --profile <YOUR_AWS_PROFILE>
```

**Note:** CloudWatch log groups (`/ecs/connect-health-streaming-dev`, `/ecs/patient-insights-backend-dev`) are not deleted by CloudFormation. Delete them separately if desired:

```bash
aws logs delete-log-group --log-group-name /ecs/connect-health-streaming-dev --profile <YOUR_AWS_PROFILE> --region us-east-1
aws logs delete-log-group --log-group-name /ecs/patient-insights-backend-dev --profile <YOUR_AWS_PROFILE> --region us-east-1
```
