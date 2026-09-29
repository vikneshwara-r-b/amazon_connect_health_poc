#!/usr/bin/env python3
"""One-off utility: fetches and prints the most recent Encounter FHIR resource
for a patient from a HealthLake R4 datastore, signed the same way
load_sample_healthlake_data.py/purge_healthlake_data.py sign their requests.

Useful for demos: after running a consultation through the app (which creates
an Encounter on stream start and marks it "finished" once the AVS is saved),
this prints that Encounter exactly as HealthLake stores it.

Usage:
    python3 get_latest_encounter.py --datastore-id <id> --patient-id <id> [--profile NAME] [--region us-east-1]
"""
import argparse
import json
import sys

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


def signed_request(method, url, credentials, region):
    headers = {"Accept": "application/fhir+json"}
    request = AWSRequest(method=method, url=url, headers=headers)
    SigV4Auth(credentials, "healthlake", region).add_auth(request)
    fn = requests.get if method == "GET" else requests.delete
    return fn(url, headers=dict(request.headers), timeout=30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datastore-id", required=True)
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile) if args.profile else boto3.Session()
    credentials = session.get_credentials()
    base_url = f"https://healthlake.{args.region}.amazonaws.com/datastore/{args.datastore_id}/r4/"

    url = f"{base_url}Encounter?subject=Patient/{args.patient_id}&_sort=-_lastUpdated&_count=1"
    resp = signed_request("GET", url, credentials, args.region)
    resp.raise_for_status()
    bundle = resp.json()

    entries = bundle.get("entry", [])
    if not entries:
        print(f"No encounters found for patient {args.patient_id}.", file=sys.stderr)
        sys.exit(1)

    encounter = entries[0]["resource"]
    print(json.dumps(encounter, indent=2))


if __name__ == "__main__":
    main()
