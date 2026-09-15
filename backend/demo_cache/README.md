# Demo Cache

Cached API responses for demo mode. When demo mode is active (via `X-Demo-Mode: true` header
or `Ctrl+Shift+D` toggle in the UI), the backend returns these cached responses instead of
calling live APIs.

## Structure

- `streaming_outputs_{patient_id_prefix}.json` — Cached streaming session outputs (SOAP notes, medical codes, AVS)
- `previsit_{patient_id_prefix}.json` — Cached Bedrock pre-visit synthesis response
- `fhir_patient_summary_{patient_id_prefix}_{section}.json` — Cached HealthLake search results for the Patient Portal (Diagnoses/Vital Signs/Recent Labs panels and the Lab results tab). `section` is `dx`, `vital`, or `lab`. Recorded once per patient at a large `_count`; the Profile "recent" panels and the full Lab results tab both read from the same cached response, slicing client-side.

## Recording New Cache Data

Set `DEMO_RECORD=true` environment variable when running the backend. All API responses will be
saved to this folder automatically. Then toggle off recording and the cached data will be served
in demo mode.
