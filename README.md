# Amazon Connect Health POC — AWS CDK (Python)

A full-stack demo of Amazon Connect Health's point-of-care capabilities — ambient documentation, pre-visit patient insights, and medical coding — deployed entirely via **AWS CDK (Python)**. This is a CDK port of [aws-samples/sample-amazon-connect-health-point-of-care](https://github.com/aws-samples/sample-amazon-connect-health-point-of-care), which originally shipped as 8 raw CloudFormation templates deployed by hand. See the [blog post](https://aws.amazon.com/blogs/industries/how-amazon-connect-health-brings-agentic-ai-to-the-point-of-care/) for the clinical workflow this app implements.

`DEPLOYMENT_GUIDE.sample.md` in this repo is the **original** CloudFormation/CLI-based guide, kept for historical reference only — none of its manual `aws cloudformation create-stack` steps apply anymore. Everything below reflects the current CDK-based workflow.

## Architecture

```
BROWSER
   │                    │                      │
   ▼                    ▼                      ▼
Frontend            Backend               Streaming
(S3 static site)    (ECS Fargate,         (ECS Fargate,
                     Python Flask)         Java WebSocket)
   │                    │                      │
   │                    ▼                      ▼
   │              HealthLake (FHIR)     ConnectHealth Streaming API
   │                    │                      │
   └──────────────► S3 (clinical notes, SOAP notes, medical codes, insights output)
```

Two topologies, controlled by one `cdk.json` flag (`useCloudFront`):
- **`useCloudFront: true`** (production-shaped): CloudFront in front of all three components — HTTPS for the frontend, an HTTPS proxy in front of the backend ALB, a WSS proxy in front of the streaming ALB.
- **`useCloudFront: false`** (bypass mode): no CloudFront at all — frontend served via S3 static website hosting, backend/streaming reached directly via their ALBs over plain HTTP/WS. Useful for quick sandbox testing. **No TLS anywhere in this mode** — fine for temporary testing, not for sharing beyond that.

### CDK stacks (`amazon_connect_health_poc/`)

| Stack | File | Purpose |
|---|---|---|
| `AmazonConnectHealthNetwork` | (inline in `app.py`) | Looks up the VPC shared by both service stacks — the account's default VPC, or the one named by `-c vpcId=vpc-...` |
| `AmazonConnectHealthPrereqs` | `connect_health_resources_stack.py` | HealthLake FHIR datastore (native CFN resource) + Connect Health Domain/Subscription (Lambda-backed custom resources — Connect Health has no CloudFormation resource type of its own) |
| `AmazonConnectHealthCognito` | `cognito_stack.py` | Optional Cognito User Pool + demo user (skippable via `enableCognito`) |
| `AmazonConnectHealthBackend` | `backend_stack.py` | ECS Fargate (Python Flask) + ALB; Docker image built by CDK itself via `DockerImageAsset` |
| `AmazonConnectHealthBackendCloudFront` | `backend_cloudfront_stack.py` | HTTPS proxy in front of the backend ALB (only when `useCloudFront=true`) |
| `AmazonConnectHealthStreaming` | `streaming_stack.py` | ECS Fargate (Java WebSocket server) + ALB |
| `AmazonConnectHealthStreamingCloudFront` | `streaming_cloudfront_stack.py` | WSS proxy in front of the streaming ALB (only when `useCloudFront=true`) |
| `AmazonConnectHealthFrontend` | `frontend_stack.py` | S3 bucket + (CloudFront+OAC, or static website hosting) for the frontend, deployed via `BucketDeployment` — `frontend/js/config.js` is templated automatically at deploy time with the real backend/WSS URLs and Cognito IDs, no manual editing needed |

Application source lives alongside the CDK code: `backend/` (Python Flask API), `streaming-service/` (Java WebSocket server), `frontend/` (static HTML/JS/CSS).

## Prerequisites

- Python 3.9+ and the AWS CDK CLI (`npm install -g aws-cdk`)
- **Docker**, running locally — `DockerImageAsset` builds and pushes the backend/streaming container images as part of `cdk deploy` (not needed for `cdk synth`)
- AWS CLI configured with a profile that has deploy permissions
- `cdk bootstrap` run once per AWS account/region

## Configure `cdk.json`

All deploy-time settings live in `cdk.json`'s `context` block (below the `@aws-cdk/*` feature-flag entries), so a deploy is just `cdk deploy` with no `-c` flags for most of these:

| Key | Default | Purpose |
|---|---|---|
| `environment` | `dev` | Suffix used in most resource names |
| `connectHealthDomainName` | `connect-health-demo` | Name for a newly-created Connect Health Domain |
| `existingDomainId` | *(empty)* | Set to reuse an existing Domain instead of creating one |
| `existingSubscriptionId` | *(empty)* | Set to reuse an existing Subscription |
| `healthlakeDatastoreName` | `connect-health-demo` | Name for a newly-created HealthLake datastore |
| `existingHealthlakeDatastoreId` | *(empty)* | Set to reuse an existing datastore |
| `corsOrigin` | `*` | Backend `CORS_ORIGINS` env var |
| `streamingCertificateArn` | *(empty)* | Optional ACM cert to terminate TLS directly on the streaming ALB |
| `frontendBucketName` | `connect-health-frontend-<account>-<environment>` | Frontend S3 bucket name (account-scoped by default for global uniqueness) |
| `demoUserEmail` | `connecthealth_demo@example.com` | Cognito demo user's email |
| `enableCognito` | `true` | Set `false` to skip the Cognito stack entirely (app runs open) |
| `useCloudFront` | `true` | See the two topologies above |

**`vpcId`** (optional, pass via `-c vpcId=vpc-...`): by default the app deploys into the account's *default* VPC. Accounts without one (common in shared/training accounts) fail at synth with `Could not find any VPCs matching ... isDefault` — and, if you deploy anyway, bogus `vpc-12345` / `s-12345` CloudFormation validation errors. Pass an existing VPC instead. It needs **at least 2 public subnets in different AZs** with a working internet gateway route: the ALBs are internet-facing and the Fargate tasks get public IPs (they pull images from ECR over the internet).

**`demoUserPassword` is deliberately not in `cdk.json`** — it's a secret, and `cdk.json` is normally committed to source control. Pass it via `-c` or an env var at deploy time instead.

**If you want Cognito verification emails to reach a real inbox you control** (rather than the `connecthealth_demo@example.com` placeholder, which receives nothing), override `demoUserEmail` via `-c demoUserEmail=<your-email>` at deploy time instead of editing it into `cdk.json` — the same reasoning as `demoUserPassword` above: don't commit a personal or test-service email address (e.g. a Mailosaur/Mailtrap inbox) into a file meant for source control.

**`cdk.context.json`** (generated by `cdk synth`/`deploy` to cache VPC lookup results) is gitignored — it contains your real AWS account ID and VPC/subnet IDs and should never be committed.

## Deploy

```bash
cdk bootstrap --profile <your-profile>          # once per account/region
cdk synth --profile <your-profile>              # sanity check
cdk deploy --profile <your-profile> \
  -c demoUserPassword=<a-strong-password> "*"
```

If the account has no default VPC, add `-c vpcId=<vpc-id>`. Before deploying, check `useCloudFront` in `cdk.json`: with `false` the ALB security groups allow TCP 80 from **Everyone (IPv4)**, with `true` only CloudFront's managed prefix list — `cdk diff` shows this as a security-group change if you flip it.

Everything after that — image builds, HealthLake datastore, Connect Health Domain/Subscription, Cognito, ECS services, CloudFront (or S3 website), and templating `config.js` with the real deployed URLs — happens in that one command.

Updating a deployed service (new code) is just `cdk deploy` again — `DockerImageAsset` detects the changed image content and CDK/CloudFormation rolls the ECS service automatically, no manual `--force-new-deployment` needed.

## After deployment: load sample FHIR data into HealthLake

A freshly deployed HealthLake datastore is **empty**, so the app shows no patients until you load some. `scripts/load_sample_healthlake_data.py` writes 3 sample patients (Elena Rodriguez, Diego Ramirez, Márcia Oliveria — matching the identities in the app's demo-mode cache) plus their conditions, observations, encounters, and medication requests (source of truth: `scripts/sample_fhir_data.py`). It calls HealthLake's FHIR REST API directly with SigV4-signed requests, because the `aws healthlake` CLI has no resource-level create/read/delete.

Run these from the repo root once `cdk deploy` has finished.

**1. Find the datastore ID** (the one CDK created — named `connect-health-demo` unless you changed `healthlakeDatastoreName`):

```bash
aws healthlake list-fhir-datastores --profile <your-profile> --region us-east-1 \
  --query "DatastorePropertiesList[?DatastoreStatus=='ACTIVE'].[DatastoreId,DatastoreName]" --output text
```

**2. Install the script's two dependencies** in any virtualenv:

```bash
python3 -m venv /tmp/loader-venv && source /tmp/loader-venv/bin/activate
pip install boto3 requests
```

**3. Load the data:**

```bash
python3 scripts/load_sample_healthlake_data.py \
  --datastore-id <datastore-id> --profile <your-profile> --region us-east-1
```

Expected output ends with `Done. Loaded 3 patients with clinical history into <datastore-id>.` The credentials must be allowed to write to the datastore (`healthlake:CreateResource`/`UpdateResource`, or admin).

**4. Verify.** Open the app (see [Running the application](#running-the-application)) — Today's Schedule should list the 3 patients. If the list is empty or counts look short right after loading, wait a minute: HealthLake's FHIR *search* index lags behind writes, so newly written resources aren't searchable instantly. Expected totals across the 3 patients: 3 Patients, 16 Conditions, 36 Observations, 7 Encounters, 19 MedicationRequests.

**Notes**
- Run the loader **once**. Patients are written by fixed ID (safe to repeat), but Conditions/Observations/Encounters/MedicationRequests are created with server-assigned IDs, so a second run duplicates them. To start over, use the reset below.
- The app itself also writes to HealthLake during a visit (a session `Encounter`, the approved SOAP note and the After Visit Summary as `DocumentReference`s) — see the architecture notes in `CLAUDE.md`.

**Reset to the initial state** (removes everything, including anything the app saved during consultations, then reloads the samples):

```bash
python3 scripts/purge_healthlake_data.py  --datastore-id <datastore-id> --profile <your-profile> --region us-east-1
python3 scripts/load_sample_healthlake_data.py --datastore-id <datastore-id> --profile <your-profile> --region us-east-1
```

The purge deletes resources one at a time (HealthLake has no bulk-delete), so it takes a while on large datastores. It keeps the datastore itself, so its ID and the deployed backend configuration stay valid.

**Cost tip.** A HealthLake datastore bills hourly (about $0.27/hr in us-east-1) for as long as it exists, plus storage. If you only need it occasionally, destroy it when idle and recreate it later — a recreated datastore gets a **new ID**, so redeploy the backend stack (its config and IAM policy reference the ID) and re-run the load steps above. Demo Mode (`Ctrl+Shift+D`) lets you show the UI without any datastore.

## Running the application

1. Open the frontend URL (CloudFront domain, or the S3 static website URL in bypass mode). Log in if Cognito is enabled.
2. **Today's Schedule** loads patients from HealthLake, with each patient's appointment slot computed dynamically (current time rounded up to the next hour, then +1 hour per patient, skipping the 12–1 PM lunch break) rather than hardcoded — see [Frontend configuration](#frontend-configuration) below to change the clinic's timezone.
3. Click a patient → the Patient Portal's **Diagnoses**, **Vital Signs**, and **Recent Lab Results** panels (plus the **Lab results** tab, full history) load live from HealthLake via a patient-scoped FHIR search. The **Pre-visit Patient Insights** panel (an AI assistant named "Ellis") generates a narrative overview, timeline, and visit priorities from the patient's FHIR history — takes 3–5 minutes on first run. If Bedrock model access isn't enabled for this account, that panel falls back to a non-LLM, keyword-based summary and shows a "Rule-Based Summary" badge so it's clear the content isn't AI-generated.
   - **Supporting evidence:** each statement links to the FHIR records it came from (click it, or "View supporting evidence"). Sources that can't be matched to a record in the patient's chart show as amber "Source not linked" entries with the cited sentence, and Patient Story text with no matching EHR source is highlighted amber, with a legend. (The insights job cites its own internal IDs, so records are matched by content — see `CLAUDE.md`.)
   - **Visit Priorities** are AI-generated and read-only. Below them, **Custom visit priorities** is yours: add, edit and delete your own items. They're saved per patient in your browser only (never sent to a server or the EHR), and they also appear, with checkboxes, in the Visit Priorities side panel during a consultation.
4. Click **Start AI Consultation** → grants mic access and streams audio to Connect Health in real time; a live transcript comes back over the WebSocket connection.
5. Stop the consultation → review the generated SOAP notes, ICD-10/CPT medical codes, and after-visit summary. **Approve & Sign** saves the SOAP note to HealthLake as a `DocumentReference` linked to the session's `Encounter`. The **Patient Visit Summary** (After Visit Summary) screen shows the Patient ID and Encounter ID, lets you edit every sub-section, and **Continue** saves the edited summary to HealthLake first (as a `DocumentReference`, then marks the Encounter finished) before moving to the final screen. If the save fails you stay on the screen with an error and can click Continue again. Medical coding is a gated preview feature and may show no codes if this AWS account hasn't been granted access — everything else works independently of it.
6. **Demo Mode** (`Ctrl+Shift+D`) runs the whole UI from cached responses with no live AWS calls — useful for a quick smoke test before HealthLake has real data.

## Frontend configuration

`frontend/js/config.js` holds settings applied client-side (separate from `cdk.json`'s deploy-time settings above):

| Setting | Default | Purpose |
|---|---|---|
| `window.APP_TIMEZONE` | `America/Lima` | IANA timezone the clinic operates in — drives the schedule screen's appointment-slot times, the "today" date header, and the header clock, so they reflect the clinic's local time rather than whatever timezone the viewer's own browser happens to be set to. Change this one line for a different clinic. |
| `window.CLINIC_PHONE` | `(555) 123-4567` (both) | Scheduling and office phone numbers shown in the UI footer and SMS follow-up template. |
| `window.COGNITO_CONFIG` | placeholder values | Templated automatically at deploy time (see the `AmazonConnectHealthFrontend` stack above) — don't hand-edit the deployed copy. |

## Troubleshooting

Issues hit and fixed while building this CDK port — worth checking first if something breaks after a code change:

| Symptom | Cause |
|---|---|
| Frontend loads but "Loading patients..." hangs forever, zero backend log activity | In bypass mode, the ALB security group must allow `0.0.0.0/0` — a leftover CloudFront-only rule silently drops the browser's connection at the SG level |
| `AccessDeniedException: ... health-agent:CreateDomain ...` | The Connect Health IAM action/ARN prefix is `health-agent`, not `connecthealth` (the latter is only the boto3 SDK client id) |
| `UnknownServiceError: Unknown service: 'healthagent'` | `boto3.client('healthagent')` is invalid — the correct id is `connecthealth` |
| `botocore.exceptions.EndpointConnectionError` resolving `runtime.runtime.health-agent...` | `StartPatientInsightsJob`/`GetPatientInsightsJob` declare a `hostPrefix: 'runtime.'` trait that botocore prepends automatically — `SERVICE_ENDPOINT` must be the bare `https://health-agent.<region>.api.aws`, not pre-prefixed with `runtime.` |
| `Unknown parameter in encounterContext: "encounterType"` | The real API only accepts `encounterReason` in that structure |
| `ReservedConcurrentExecutions ... decreases account's UnreservedConcurrentExecution below its minimum` | Low-quota sandbox accounts can't afford per-Lambda concurrency reservations on one-shot custom resources — just remove `reserved_concurrent_executions` |
| Docker build fails on `eclipse-temurin:*-alpine`, "no match for platform in manifest" | Apple Silicon defaults to `arm64`; pin `platform=ecr_assets.Platform.LINUX_AMD64` on `DockerImageAsset` (matches Fargate's `X86_64` runtime anyway) |
| Empty ICD-10/CPT codes after a consultation, everything else populated | Medical coding (`GenerateMedicalCodes`) is a gated preview feature — check `aws s3 ls` under the session's `post-stream-action/` prefix for a missing `medicalCodes.json` to confirm |
| Frontend loads but there are no patients | The datastore is empty — [load the sample data](#after-deployment-load-sample-fhir-data-into-healthlake) |
| `cdk synth`/`deploy`: `Could not find any VPCs matching ... isDefault`, plus `VpcId: 'vpc-12345' does not match format` / `Subnets.0: 's-12345'` errors | The account has no default VPC — the failed lookup leaves CDK's placeholder IDs everywhere. Deploy with `-c vpcId=<vpc-id>` (a VPC with 2+ public subnets in different AZs) |
| `AWS::ECS::Service` `CREATE_FAILED`: "ECS Deployment Circuit Breaker was triggered" | Tasks never started. With `assign_public_ip=True`, the usual cause is a VPC with no working internet route — check the subnets' route table for a `0.0.0.0/0` route to a live internet gateway (a deleted IGW leaves the route as `blackhole`), so Fargate can't pull the image from ECR. The rollback deletes the log group, so reproduce with `--no-rollback` to read the task's stopped reason |
| "Source not linked" on supporting evidence | Expected for citations that can't be matched to a chart record; the insights job cites internal IDs (`Observation/14`), not HealthLake IDs, and sometimes labels a record with the wrong type. If *everything* is unlinked, the resource lookup (`/api/fhir/patient/<id>/resources`) is failing or the page is stale — hard-refresh after a frontend deploy |
| `cdk diff` shows the ALB security group changing from a `pl-...` prefix list to `Everyone (IPv4)` | `useCloudFront` in `cdk.json` is `false` while the stack was deployed with CloudFront — set it back to `true` |
| Local backend (`python server.py`) returns `403 Forbidden` with `Server: AirTunes/...` for every request, on macOS | The OS's own AirPlay Receiver service squats on port 5000/`localhost` — use `http://127.0.0.1:5000` instead, or disable AirPlay Receiver (System Settings → General → AirDrop & Handoff) if you need the `localhost` hostname specifically |

## Tests

```bash
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/unit
```

## Cleanup

```bash
cdk destroy --profile <your-profile> -c vpcId=<vpc-id-if-you-used-one> -c demoUserPassword=<any-value> "*"
```

(`demoUserPassword` only lets CDK build the stacks; any value works when destroying.)

S3 buckets and CloudWatch log groups are configured to auto-delete with their stacks (`RemovalPolicy.DESTROY` + `auto_delete_objects=True`) — no manual emptying needed, unlike the original CloudFormation guide.

**Removing just HealthLake + the Connect Health Domain/Subscription** (`AmazonConnectHealthPrereqs` — the costly, disposable resources: HealthLake bills hourly + storage for as long as it exists) **without touching Backend/Streaming/Frontend/Cognito**:

```bash
cdk destroy --profile <your-profile> AmazonConnectHealthPrereqs
```

This works on its own — `AmazonConnectHealthPrereqs` publishes its IDs to SSM Parameter Store rather than handing them directly to the other stacks, so there's no CloudFormation export tying its lifecycle to theirs. Backend/Streaming keep running throughout, though anything that calls HealthLake or Connect Health will error until the datastore/domain/subscription exist again (expected — same as a brief outage of those two services).

**To bring it back:**
```bash
cdk deploy --profile <your-profile> -c vpcId=<vpc-id-if-you-used-one> -c demoUserPassword=<pw> AmazonConnectHealthPrereqs
cdk deploy --profile <your-profile> -c vpcId=<vpc-id-if-you-used-one> -c demoUserPassword=<pw> AmazonConnectHealthBackend AmazonConnectHealthStreaming
```
The second command is required: Backend/Streaming only pick up the *new* datastore/domain/subscription IDs (via SSM) when they're redeployed — their ECS task environment variables are set at deploy time, not re-read live. Recreating gets a **new datastore ID**, so re-run the [sample-data load](#after-deployment-load-sample-fhir-data-into-healthlake) afterwards.

## Security notes

- **Nothing secret is committed.** No credentials, tokens, real account IDs or resource IDs are in the repo or its git history (checked). `demoUserPassword` is deliberately passed at deploy time with `-c`, never stored in `cdk.json`. If a password was ever pasted into a chat, terminal log or shared screen, reset the Cognito demo user's password (or redeploy with a new one).
- **Files that do contain real values are gitignored:** `cdk.context.json` (account ID, VPC/subnet IDs), `cdk.out/`, `.claude/`. Keep them out of commits.
- **Sample patients are demo data.** Elena Rodriguez, Diego Ramirez and Márcia Oliveria come from the upstream AWS sample and are treated as synthetic; the repo contains no real patient data. The phone numbers are fictional `(555)` placeholders and the default demo user email is `connecthealth_demo@example.com`. If you replace them with real values, do it via deploy-time `-c` overrides rather than committing them.
- Bypass mode (`useCloudFront: false`) has no TLS and opens the ALBs to the internet — sandbox only.

## Known limitations (inherited from the upstream sample app, not this CDK port)

- `/api/send-sms` depends on a named local AWS CLI profile (`SMS_AWS_PROFILE`) for a separate Pinpoint SMS account — this can't resolve inside an ECS container and doesn't work as deployed.
- Bedrock model access ("Claude Sonnet 4.5") must be enabled once per account in the Bedrock console — not a CloudFormation/CDK-manageable setting.
- Multi-region deployment (e.g. `us-west-2`, also supported by Connect Health) needs more than changing `env.region` — a few hardcoded `us-east-1` defaults remain in the Bedrock inference-profile ARN and some app config.

## License

MIT-0, per the upstream sample repository.
