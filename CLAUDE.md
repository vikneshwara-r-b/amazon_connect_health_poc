# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A CDK (Python) port of an AWS sample app demoing Amazon Connect Health's point-of-care capabilities (ambient clinical documentation, pre-visit patient insights, medical coding). Three independently deployed services — `backend/` (Python Flask), `streaming-service/` (Java WebSocket server), `frontend/` (static HTML/JS/CSS) — provisioned by CDK stacks in `amazon_connect_health_poc/`. `DEPLOYMENT_GUIDE.sample.md` is the original (pre-CDK) CloudFormation guide, kept for historical reference only — its manual steps don't apply to this codebase.

## Commands

**CDK (from repo root):**
```bash
cdk synth --profile <profile>                                   # sanity check, no AWS calls beyond context lookups
cdk deploy --profile <profile> -c demoUserPassword=<pw> "*"     # deploy everything
cdk deploy --profile <profile> AmazonConnectHealthFrontend       # redeploy just one stack (e.g. after a frontend JS/HTML edit)
cdk destroy --profile <profile> "*"
```
All other deploy-time config lives in `cdk.json`'s `context` block (not `-c` flags) — see the table in README.md. `demoUserPassword` and any real (non-`example.com`) `demoUserEmail` must be passed via `-c`, never committed to `cdk.json`.

**Python (CDK app + its tests):**
```bash
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest tests/unit                          # CDK stack synthesis tests
pytest tests/unit/test_amazon_connect_health_poc_stack.py::test_name   # single test
```

**Backend (Flask, local dev only — in deployment it runs inside the ECS container via `DockerImageAsset`):**
```bash
cd backend && pip install -r requirements.txt
python server.py                           # reads config from backend/config.py env vars
```
Backend's own unit tests: `backend/tests/test_config.py`.

**Streaming service (Java):**
```bash
cd streaming-service
mvn compile
mvn test                                    # runs StreamingConfigTest
mvn compile exec:java                       # run locally (main class: StreamingServer)
mvn package                                 # shaded fat-jar, used by the Docker build
```
`CreateSubscription.java` is a standalone one-off bootstrap utility, not part of the normal server startup — run explicitly via `mvn compile exec:java -Dexec.mainClass=com.example.connecthealth.CreateSubscription`.

**Frontend:** no build step — plain HTML/JS/CSS deployed as-is via S3 `BucketDeployment`. Editing any file under `frontend/` requires redeploying `AmazonConnectHealthFrontend` for changes to reach the browser. `frontend/js/config.js` is templated at deploy time (backend/WSS URLs, Cognito IDs substituted into `Source.data` tokens) — don't hand-edit the deployed copy's values, edit the CDK stack that generates it.

**One-off data scripts** (`scripts/`, run from repo root with a venv that has `boto3`+`requests`):
```bash
python3 scripts/load_sample_healthlake_data.py --datastore-id <id> --profile <profile> --region us-east-1
python3 scripts/purge_healthlake_data.py --datastore-id <id> --profile <profile> --region us-east-1
```
Both operate directly on HealthLake's FHIR REST API via manually SigV4-signed `requests` calls (`botocore.auth.SigV4Auth` + `AWSRequest`) — the `aws healthlake` CLI has no resource CRUD, only datastore-management operations. `sample_fhir_data.py`'s `PATIENTS` list is the source of truth for the 3 demo patients; it's written to match the narrative content already baked into `backend/demo_cache/patient_insights_*.json`, so if you add clinical data for a patient here, keep it consistent with that patient's cached narrative or the two will visibly disagree in the UI.

## Architecture

### Data flow is asymmetric: HealthLake is read-only from this app's perspective

Every HealthLake interaction in `backend/server.py` is a `GET`/FHIR-search — patient list, `GET /api/fhir/<type>/<id>` (single resource), `GET /api/fhir/patient/<id>/summary?section={diagnoses|vitals|labs}` (patient-scoped search — powers the Patient Portal's Diagnoses/Vital Signs/Recent Labs panels and the Lab results tab), and the `fhirEndpoint` handed to AWS's own `StartPatientInsightsJob` for *it* to read from. There is no `PUT`/`POST` to HealthLake anywhere in the codebase. Nothing generated during a visit (SOAP note, medical codes, after-visit summary, patient insights) is ever written back into the FHIR datastore — it all lands in S3 only, generated and stored by AWS-managed jobs. A live consultation produces zero durable change to a patient's HealthLake chart.

The single-GET route and the patient-scoped search route share a SigV4-signing helper (`_healthlake_request()`) and per-resource-type field extraction (`_extract_condition_fields()`, `_extract_observation_fields()`) in `backend/server.py` — if you add a new FHIR resource type or search section, extend those shared functions rather than duplicating the signing/parsing logic a third time. HealthLake's FHIR search API caps `_count` at 100 (a 400 above that) — the frontend requests `_count=100` once per section and slices client-side for "recent" vs "full history" views (`frontend/js/patient-data.js`) rather than issuing separate large/small requests.

### Streaming sessions are not linked to patient records

`frontend/js/streaming.js` generates `sessionId` via `crypto.randomUUID()` with no `patientId` passed anywhere in that flow. SOAP notes, medical codes, and after-visit summaries are all fetched from S3 by `sessionId` (`backend/server.py`'s `/api/streaming/session/<session_id>/...` routes), and that linkage exists only transiently in browser memory during one active consultation — there is no way to look up "the AVS/SOAP note for patient X" after the fact.

### Two independent AI pipelines — don't conflate them

1. **SOAP notes / medical codes / after-visit summary**: entirely AWS-managed. `streaming-service/.../WebSocketEndpoint.java` starts a `StartMedicalScribeListeningSession` with `postStreamActionSettings.clinicalNoteGenerationSettings.noteTemplateSettings.managedTemplate.templateType("PHYSICAL_SOAP")` and an S3 output URI; AWS generates everything server-side. Bedrock plays no role here at all.
2. **Pre-visit Patient Insights narrative ("Ellis")**: `backend/server.py`'s `/api/synthesize-previsit` (+ legacy `/api/synthesize-narrative`, `/api/synthesize-priorities`) calls `bedrock-runtime.invoke_model` directly, feeding it the raw `PatientSummary.Sections` text from `StartPatientInsightsJob`'s output. If Bedrock model access isn't granted in the account (Bedrock console → Model access, us-east-1 — this is a manual, console-only step with no CDK/CLI equivalent), these endpoints 500 with `ValidationException: Operation not allowed`, and `frontend/previsit-iframe.html` falls back to non-LLM content: **Patient Story** becomes a bare `age gender - overview text` template (the `overview` text itself is still real, from Connect Health's own `StartPatientInsightsJob` summary — not Bedrock), and **Visit Priorities** is generated by `generateVisitPriorities()`/`generateVisitChecklist()`, a pure regex/keyword matcher over that overview text (elevated uric acid, sed rate, colchicine, recent inpatient care, etc. — a fixed, narrow set of patterns, not general-purpose). This is no longer silent: both fallback sections show a "Rule-Based Summary" badge (`#patientStoryFallbackBadge` / `#visitPrioritiesFallbackBadge`) so it isn't mistaken for genuine Bedrock synthesis. Demo-mode cached responses (`backend/demo_cache/synthesize_previsit_*.json`) are real curated content and correctly never show this badge.

### Demo mode is a response cache, not a mock

`backend/demo_mode.py`: when the frontend sends `X-Demo-Mode: true` (toggled via `Ctrl+Shift+D`), matching endpoints return a file from `backend/demo_cache/` instead of calling AWS. Cache files are named `{endpoint}_{first-8-hex-of-id}.json` (e.g. `fhir_patient_summary_{patientIdPrefix}_{dx|vital|lab}.json` for the patient-scoped FHIR search route — deliberately short section tokens, since `_cache_key()` truncates the identifier to 16 chars). To capture new ones, run the backend with `DEMO_RECORD=true` and exercise the live flow once — real responses get written to `backend/demo_cache/` automatically (the `fhir_patient_summary_*.json` files were instead generated directly from `scripts/sample_fhir_data.py`'s `PATIENTS` data, since that's the guaranteed source of truth for what's actually loaded into HealthLake). This means demo mode and live mode can visibly diverge in formatting (e.g. cached data uses `*`-bullet item lists; the live API does not) — parsing code in `previsit-iframe.html` needs to tolerate both shapes, not just whichever one was on hand when a given parser was written.

### Frontend date/time display uses a configured clinic timezone, not the browser's

`frontend/js/config.js` sets `window.APP_TIMEZONE` (an IANA name, e.g. `America/Lima`) and exposes `window.getZonedNow(timeZone)`, which returns `{year, month, day, hour, minute, second}` for that timezone via `Intl.DateTimeFormat(...).formatToParts()` — independent of whatever timezone the viewer's own browser/OS happens to be set to. Any code that needs the *current* wall-clock date/time for display (schedule appointment slots, the "today" date header, the header sync-time clock, age-derived birth-year estimates) must go through `getZonedNow()`/pass `timeZone: window.APP_TIMEZONE` to `toLocaleDateString`/`toLocaleTimeString`, not call `new Date().getHours()`/`getFullYear()` etc. directly — otherwise it silently follows the browser's local timezone instead of the clinic's. This does **not** apply to elapsed-duration math (consultation timers, token-expiry checks in `auth.js`) — subtracting two timestamps is timezone-invariant regardless of what zone either one was captured in — nor to formatting an already-known calendar date (FHIR birthdate/onset-date strings in `previsit-iframe.html`), which isn't a "current time" computation at all.

### Two deploy topologies, one flag

`cdk.json`'s `useCloudFront` context key controls everything: `true` puts CloudFront in front of all three components (HTTPS everywhere, `backend_cloudfront_stack.py` / `streaming_cloudfront_stack.py`); `false` is a plain-HTTP/WS bypass mode (no CloudFront at all, frontend via S3 static website hosting) — useful when an account is waiting on CloudFront's account-verification gate. Bypass mode has no TLS anywhere; treat it as sandbox-only.

### Known non-obvious gotchas (verified by reading the actual code, not assumed)

- `SERVICE_ENDPOINT` (backend) must be the bare `https://health-agent.<region>.api.aws` — botocore auto-prepends a `runtime.` `hostPrefix` for `StartPatientInsightsJob`/`GetPatientInsightsJob`; pre-prefixing it yourself doubles it into an unresolvable host.
- The Connect Health IAM action/ARN prefix is `health-agent`, but the boto3 client id is `connecthealth` (`boto3.client('connecthealth')`) — `healthagent` is not a valid client id anywhere.
- HealthLake's FHIR *search* API (as opposed to a direct-by-ID read) has a short indexing lag after writes — a `StartPatientInsightsJob` fired immediately after a bulk load can come back with only bare Patient demographics and nothing else, even though the data is present and becomes searchable moments later.
- The streaming audio pipeline is single-channel/mono end-to-end (`frontend/js/streaming.js` requests `channelCount: 1`), and `WebSocketEndpoint.java` never sets `channelDefinitions` on the Connect Health session. The API supports (and expects, for reliable role attribution) 2 channel-separated audio streams with explicit `PATIENT`/`CLINICIAN` roles; without it, speaker role comes from unreliable automatic diarization on a single mixed feed, which can misattribute turns.
- Medical coding (`GenerateMedicalCodes`) is a gated preview feature — empty ICD-10/CPT codes after a consultation, with everything else populated, means the account lacks access, not a bug. Check for a missing `medicalCodes.json` under the session's `post-stream-action/` S3 prefix to confirm.
- The "Flag a Moment" UI feature (`frontend/js/main.js`, spacebar or the flag button during a consultation) only updates an in-memory counter and shows a toast — the flagged-moments array is never rendered anywhere, never sent to the backend, and resets on every new consultation. Don't assume it does anything beyond the visual feedback.
- `/api/send-sms` depends on a named local AWS CLI profile (`SMS_AWS_PROFILE`) for a separate Pinpoint account — this can't resolve inside an ECS container and does not work as deployed.
- On macOS, `curl http://localhost:5000/...` (the backend's default port) can silently hit the OS's own AirPlay Receiver service instead of the Flask dev server — it returns `403 Forbidden` with `Server: AirTunes/...` in the headers, easy to mistake for an app bug. `http://127.0.0.1:5000/...` reaches the actual backend; AirPlay Receiver only squats on the `localhost` hostname. Turning off AirPlay Receiver (System Settings → General → AirDrop & Handoff) avoids this if you need the `localhost` hostname to work, e.g. for same-origin frontend/backend testing.
- `frontend/index.html`'s `.patient-portal-background` is shown/hidden via a JS-set **inline** `style.display`, not a CSS class — and an inline style always wins over any stylesheet rule for that same property, `!important` or not. Its CSS declares `display: flex; flex-direction: column` (so `.main-content` can correctly flex-fill the remaining height under `.tab-nav`); if the JS that shows it ever sets `.style.display = 'block'` instead of `'flex'`, that layout silently collapses back to plain block flow and `.main-content` grows past the viewport with no visible error — this exact bug reappeared once already (see `window.openPatient` in `frontend/index.html`) after the CSS was changed without checking the JS side.
