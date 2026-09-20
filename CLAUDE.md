# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A CDK (Python) port of an AWS sample app demoing Amazon Connect Health's point-of-care capabilities (ambient clinical documentation, pre-visit patient insights, medical coding). Three independently deployed services — `backend/` (Python Flask), `streaming-service/` (Java WebSocket server), `frontend/` (static HTML/JS/CSS) — provisioned by CDK stacks in `amazon_connect_health_poc/`. `DEPLOYMENT_GUIDE.sample.md` is the original (pre-CDK) CloudFormation guide, kept for historical reference only — its manual steps don't apply to this codebase.

## Commands

**CDK (from repo root):**
```bash
cdk synth --profile <profile>                                   # sanity check, no AWS calls beyond context lookups
cdk deploy --profile <profile> -c demoUserPassword=<pw> "*"     # deploy everything (add -c vpcId=vpc-... if the account has no default VPC)
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
Both operate directly on HealthLake's FHIR REST API via manually SigV4-signed `requests` calls (`botocore.auth.SigV4Auth` + `AWSRequest`) — the `aws healthlake` CLI has no resource CRUD, only datastore-management operations. `purge_healthlake_data.py` deletes `DocumentReference` (the app's saved SOAP notes/AVS) first, then everything else, so a purge + load is the way to reset a datastore to its initial state (keeps the datastore ID). `sample_fhir_data.py`'s `PATIENTS` list is the source of truth for the 3 demo patients; it's written to match the narrative content already baked into `backend/demo_cache/patient_insights_*.json`, so if you add clinical data for a patient here, keep it consistent with that patient's cached narrative or the two will visibly disagree in the UI.

## Architecture

### HealthLake data flow: mostly read, with three write-backs

Reads (`backend/server.py`): patient list, `GET /api/fhir/<type>/<id>` (single resource), `GET /api/fhir/patient/<id>/summary?section={diagnoses|vitals|labs}` (powers the Diagnoses/Vital Signs/Recent Labs panels and the Lab results tab), `GET /api/fhir/patient/<id>/resources` (compact Observation/MedicationRequest/Condition/Encounter list used to resolve insights-job evidence), and the `fhirEndpoint` handed to AWS's own `StartPatientInsightsJob`.

Writes (SigV4 `POST`/`PUT` via `_healthlake_request()`; IAM `healthlake:CreateResource`/`UpdateResource` in `backend_stack.py`; all skipped in demo mode):
1. `POST /api/streaming/session/start` creates an `Encounter` (`in-progress`) when streaming starts, linking the session to the patient (`window.currentEncounterId`).
2. `POST /api/fhir/patient/<id>/document-reference` saves the approved SOAP note (`kind: "soap"`, LOINC 34117-2) on Approve & Sign, and the clinician-edited After Visit Summary (`kind: "avs"`, LOINC 69730-0) when **Continue** is clicked in the Patient Visit Summary overlay (`continueAfterVisitSummary()` saves first and only advances if the save succeeds; unchanged content is not re-saved). Both link to the Encounter.
3. `POST /api/fhir/encounter/<id>/finish` sets the Encounter to `finished` with `period.end` after the AVS is saved.

Everything else generated during a visit (medical codes, transcript, raw AWS-generated SOAP/AVS, patient insights) stays in S3 only. `_healthlake_request()` and the per-type field extractors (`_extract_condition_fields()`, `_extract_observation_fields()`, `_extract_medication_fields()`) are shared — extend them rather than duplicating signing/parsing. HealthLake's FHIR search caps `_count` at 100 (a 400 above that); the frontend requests `_count=100` once per section and slices client-side.

The frontend guards against double saves (`window._soapSaving`, `window._avsSaving`); edited AVS content lives in `window.editedAvs` and is what the final overlay and the EHR save use, not the original S3 copy. AI-generated Visit Priorities are read-only. `previsit-iframe.html` has a separate **Custom visit priorities** subsection (add/edit/delete) stored per patient in `localStorage['customVisitPriorities:<patientId>']` — browser-local only, never sent to the backend or HealthLake.

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
- `/api/send-sms` depends on a named local AWS CLI profile (`SMS_AWS_PROFILE`) for a separate Pinpoint account — this can't resolve inside an ECS container and does not work as deployed.
- On macOS, `curl http://localhost:5000/...` (the backend's default port) can silently hit the OS's own AirPlay Receiver service instead of the Flask dev server — it returns `403 Forbidden` with `Server: AirTunes/...` in the headers, easy to mistake for an app bug. `http://127.0.0.1:5000/...` reaches the actual backend; AirPlay Receiver only squats on the `localhost` hostname. Turning off AirPlay Receiver (System Settings → General → AirDrop & Handoff) avoids this if you need the `localhost` hostname to work, e.g. for same-origin frontend/backend testing.
- `frontend/index.html`'s `.patient-portal-background` is shown/hidden via a JS-set **inline** `style.display`, not a CSS class — and an inline style always wins over any stylesheet rule for that same property, `!important` or not. Its CSS declares `display: flex; flex-direction: column` (so `.main-content` can correctly flex-fill the remaining height under `.tab-nav`); if the JS that shows it ever sets `.style.display = 'block'` instead of `'flex'`, that layout silently collapses back to plain block flow and `.main-content` grows past the viewport with no visible error — this exact bug reappeared once already (see `window.openPatient` in `frontend/index.html`) after the CSS was changed without checking the JS side.
- Patient Insights job evidence refs are job-internal, not HealthLake IDs: `summary.json` cites `Patient/1`, `Observation/14`, `MedicationRequest/25` (one global sequence, no mapping file, no API field to translate them; orderings by id/lastUpdated/`$everything` don't reproduce it), so `GET /api/fhir/<type>/<ref-id>` always 404s. `frontend/previsit-iframe.html`'s `resolveEvidenceRef()` instead matches each ref's cited narrative text against the patient's real resources from `GET /api/fhir/patient/<id>/resources`. The job's line wording varies between runs (`Body weight: 299.8 lbs on 11/01/2025` vs `Body weight 299.8 lbs on 11/01/2025`; with or without "as of <date>"), so matching is format-independent scoring (`_evidenceScore()`): Observations need the exact value (as a whole number token, dates stripped first) + name words + date; Medications/Conditions match on distinctive name words; Encounters on date. Single-citation lines are matched first, then leftover refs from multi-citation sentences by elimination of already-claimed records; ties stay unlinked. Unresolvable refs render as amber "Source not linked" (badge + cited sentence; the job sometimes labels a record with the wrong type, e.g. a medication start cited as `Observation/…`, which type-specific matching can't resolve), and `annotateUnsourcedEvidence()` shades Patient Story text with no linked source amber (this fetches `/resources` eagerly for the Patient Story; the evidence popover reuses the cached result). Demo mode skips all of this (the demo route returns placeholders for any ref). Don't reintroduce format-specific regexes here — an earlier colon-only version resolved 4 of 25 refs once the job changed its wording.
- **No default VPC → pass `-c vpcId=`.** `app.py` looks up the default VPC unless `vpcId` is set; when the lookup fails CDK substitutes dummy IDs (`vpc-12345`, `s-12345`) that then fail CloudFormation validation on every SG/ALB/target group/ECS service, which hides the real cause. The chosen VPC needs 2+ public subnets in different AZs *and* a live internet-gateway route: Fargate tasks use `assign_public_ip=True` and pull images over the internet, so a `blackhole` `0.0.0.0/0` route (deleted IGW) shows up only as "ECS Deployment Circuit Breaker was triggered" — and the rollback deletes the log group, leaving no logs.
- `cdk.json`'s `useCloudFront: false` makes both ALB security groups allow TCP 80 from `Everyone (IPv4)` (bypass mode); `true` restricts them to CloudFront's managed prefix list. A `cdk diff` swapping `pl-…` for `Everyone (IPv4)` means the flag is wrong for the deployed topology.
- HealthLake datastore cost: the datastore is created by `CfnFHIRDatastore` with no `AnalyticsConfiguration`, which the service defaults to `ENABLED`, and that is what bills as the Advanced tier (`AdvancedDataStorage` usage type, $0.37/GB-mo vs $0.25 for `FHIRDataStorage`). `AWS::HealthLake::FHIRDatastore`/`CfnFHIRDatastore` cannot set it (the CFN schema lags the API), but `UpdateFHIRDatastore` accepts `AnalyticsConfiguration={'Status': 'DISABLED'}` on a live datastore with no data loss; for CDK it would need a Lambda-backed custom resource like the Domain/Subscription ones in `connect_health_resources_stack.py`. Not applied yet. The hourly rate ($0.27/hr us-east-1) is the same either way, so destroying an idle datastore is the only way to stop it; a recreated one gets a new ID (redeploy the Backend stack, re-run the loader).
- **Still-static UI content (not from HealthLake):** the red "Allergies" badge in the patient header and the whole Allergies panel (Penicillins / Onion / Bee venom) in `frontend/index.html` are fixed text shown for every patient — there is no `AllergyIntolerance` data or route anywhere. The schedule's visit-type badge and duration are a fixed rotating list by position (`visitTypes`/`durations` in `index.html`), the pre-visit header's "Diabetic follow-up" is a placeholder until replaced by "<name> - Follow-up Visit", and `encounterReason: 'Follow-up visit'` is hardcoded on both the insights-job start (`index.html`) and the priorities synthesis call (`previsit-iframe.html`). No appointment data exists in HealthLake.
- The "Since last visit" section was removed from the pre-visit page. The Bedrock prompt in `backend/server.py` still asks for a SINCE LAST VISIT block (its "No events documented since the last visit." fallback sentence comes from that prompt, not the UI); the page just ignores it.
- Custom visit priorities (pre-visit page, `localStorage['customVisitPriorities:<patientId>']`) are also read by the parent page: `getCustomVisitPriorities()` in `frontend/js/main.js` renders them in the consultation screen's Visit Priorities side panel, and a `storage` event listener refreshes the panel when the iframe edits them. Same origin is what makes this work.
- **Secrets/PII:** the repo and its history contain no credentials or real account/resource IDs (`cdk.context.json`, `cdk.out/`, `.claude/` are gitignored and hold the real ones); sample patients are synthetic upstream demo data. See "Security notes" in README.md. Never put `demoUserPassword` or real IDs in tracked files.
