# Demo Cache

Cached API responses for demo mode. When demo mode is active (via `X-Demo-Mode: true` header
or `Ctrl+Shift+D` toggle in the UI), the backend returns these cached responses instead of
calling live APIs.

## Structure

- `streaming_outputs_{patient_id_prefix}.json` — Cached streaming session outputs (SOAP notes, medical codes, AVS)
- `previsit_{patient_id_prefix}.json` — Cached Bedrock pre-visit synthesis response

## Recording New Cache Data

Set `DEMO_RECORD=true` environment variable when running the backend. All API responses will be
saved to this folder automatically. Then toggle off recording and the cached data will be served
in demo mode.
