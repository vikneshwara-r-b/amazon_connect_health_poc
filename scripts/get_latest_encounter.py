#!/usr/bin/env python3
"""One-off utility: fetches and prints the most recent Encounter FHIR resource
for a patient from a HealthLake R4 datastore, signed the same way
load_sample_healthlake_data.py/purge_healthlake_data.py sign their requests.

Useful for demos: after running a consultation through the app (which creates
an Encounter on stream start and marks it "finished" once the AVS is saved),
this prints that Encounter exactly as HealthLake stores it.

With --notes {soap,avs}, also fetches and prints the clinician's note
(DocumentReference) linked to that same Encounter -- the approved SOAP note
(kind="soap", written on Approve & Sign) or the finalized After Visit Summary
(kind="avs", written when Continue is clicked on the Patient Visit Summary
screen). Only prints something once the consultation has gone through that
step -- see CLAUDE.md's HealthLake write-back notes. The AWS-generated raw
SOAP/AVS that exists before that point lives in S3 only, not HealthLake, so
this won't find it.

Usage:
    python3 get_latest_encounter.py --datastore-id <id> --patient-id <id> \
        [--notes soap|avs] [--profile NAME] [--region us-east-1]
"""
import argparse
import base64
import json
import sys
from urllib.parse import quote

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# kind -> LOINC code, same mapping as backend/server.py's DOCUMENT_KINDS
DOCUMENT_KINDS = {
    "soap": "34117-2",
    "avs": "69730-0",
}


def signed_request(method, url, credentials, region):
    headers = {"Accept": "application/fhir+json"}
    request = AWSRequest(method=method, url=url, headers=headers)
    SigV4Auth(credentials, "healthlake", region).add_auth(request)
    fn = requests.get if method == "GET" else requests.delete
    return fn(url, headers=dict(request.headers), timeout=30)


def fetch_latest_encounter(base_url, patient_id, credentials, region):
    # The "/" in "Patient/<id>" must be percent-encoded (%2F) in the literal URL
    # string used for BOTH signing and the actual request. botocore's SigV4Auth
    # always normalizes query values to their strictly-encoded form (%2F) when
    # computing the canonical request, regardless of the input -- but `requests`
    # sends a raw, unencoded "/" through unchanged. That mismatch between what
    # got signed and what's actually on the wire is what AWS rejects with
    # "SignatureDoesNotMatch" (a 403 with a signature-mismatch body, distinct
    # from an IAM AccessDenied 403).
    subject_param = quote(f"Patient/{patient_id}", safe="")
    url = f"{base_url}Encounter?subject={subject_param}&_sort=-_lastUpdated&_count=1"
    resp = signed_request("GET", url, credentials, region)
    resp.raise_for_status()
    entries = resp.json().get("entry", [])
    return entries[0]["resource"] if entries else None


def fetch_document_reference(base_url, encounter_id, kind, credentials, region):
    # DocumentReference's search param for its context.encounter reference is
    # "encounter" per the FHIR R4 spec. Same percent-encoding requirement as
    # the Patient/<id> reference above.
    encounter_param = quote(f"Encounter/{encounter_id}", safe="")
    url = f"{base_url}DocumentReference?encounter={encounter_param}&_sort=-_lastUpdated&_count=20"
    resp = signed_request("GET", url, credentials, region)
    resp.raise_for_status()
    entries = resp.json().get("entry", [])

    loinc_code = DOCUMENT_KINDS[kind]
    for entry in entries:
        resource = entry["resource"]
        codings = resource.get("type", {}).get("coding", [])
        if any(c.get("code") == loinc_code for c in codings):
            return resource
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datastore-id", required=True)
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--notes", choices=sorted(DOCUMENT_KINDS), default=None,
                         help="also fetch the clinician note linked to the latest "
                              "encounter: soap = approved SOAP note, "
                              "avs = finalized After Visit Summary")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile) if args.profile else boto3.Session()
    credentials = session.get_credentials()
    base_url = f"https://healthlake.{args.region}.amazonaws.com/datastore/{args.datastore_id}/r4/"

    encounter = fetch_latest_encounter(base_url, args.patient_id, credentials, args.region)
    if not encounter:
        print(f"No encounters found for patient {args.patient_id}.", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(encounter, indent=2))

    if not args.notes:
        return

    encounter_id = encounter["id"]
    doc_ref = fetch_document_reference(base_url, encounter_id, args.notes, credentials, args.region)
    if not doc_ref:
        print(
            f"\nNo '{args.notes}' DocumentReference found for encounter {encounter_id} "
            f"-- it may not have been saved yet (Approve & Sign for SOAP, or Continue "
            f"on Patient Visit Summary for AVS), or it's still only in S3.",
            file=sys.stderr,
        )
        sys.exit(1)

    attachment = doc_ref.get("content", [{}])[0].get("attachment", {})
    text = base64.b64decode(attachment.get("data", "")).decode("utf-8") if attachment.get("data") else ""

    print(f"\n{'=' * 60}")
    print(f"DocumentReference: {doc_ref.get('id')}")
    print(f"Kind: {args.notes} (LOINC {DOCUMENT_KINDS[args.notes]})")
    print(f"Date: {doc_ref.get('date', 'unknown')}")
    print("-" * 60)
    print(text)


if __name__ == "__main__":
    main()
