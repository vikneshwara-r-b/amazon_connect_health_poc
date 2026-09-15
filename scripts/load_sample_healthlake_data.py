#!/usr/bin/env python3
"""One-off loader: writes scripts/sample_fhir_data.py's Patient/Condition/
Observation/Encounter/MedicationRequest resources into a HealthLake FHIR R4
datastore via the FHIR REST API, SigV4-signed the same way backend/server.py
signs its own HealthLake requests (botocore SigV4Auth + requests -- HealthLake
has no CRUD support in the `aws healthlake` CLI, only datastore-management
operations, so direct signed HTTPS calls are the only option, matching what
DEPLOYMENT_GUIDE.sample.md's Prerequisites section says to do).

Usage:
    python3 load_sample_healthlake_data.py --datastore-id <id> [--profile NAME] [--region us-east-1]
"""
import argparse
import sys

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from sample_fhir_data import (
    PATIENTS,
    condition_resources,
    encounter_resources,
    medication_request_resources,
    observation_resources,
    patient_resource,
)


def signed_request(method, url, credentials, region, body=None):
    headers = {"Content-Type": "application/fhir+json", "Accept": "application/fhir+json"}
    request = AWSRequest(method=method, url=url, headers=headers, data=body)
    SigV4Auth(credentials, "healthlake", region).add_auth(request)
    fn = requests.put if method == "PUT" else requests.post
    return fn(url, headers=dict(request.headers), data=body, timeout=30)


def put_resource(base_url, resource, credentials, region):
    url = f"{base_url}{resource['resourceType']}/{resource['id']}"
    import json

    resp = signed_request("PUT", url, credentials, region, body=json.dumps(resource))
    resp.raise_for_status()
    return resp.json()


def post_resource(base_url, resource, credentials, region):
    import json

    url = f"{base_url}{resource['resourceType']}"
    resp = signed_request("POST", url, credentials, region, body=json.dumps(resource))
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datastore-id", required=True)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile) if args.profile else boto3.Session()
    credentials = session.get_credentials()
    base_url = f"https://healthlake.{args.region}.amazonaws.com/datastore/{args.datastore_id}/r4/"

    for p in PATIENTS:
        label = f"{p['given']} {p['family']} ({p['id'][:8]})"

        patient = patient_resource(p)
        put_resource(base_url, patient, credentials, args.region)
        print(f"[Patient] {label} -> loaded")

        for cond in condition_resources(p):
            post_resource(base_url, cond, credentials, args.region)
        print(f"  [Condition] {len(p['conditions'])} loaded")

        for obs in observation_resources(p):
            post_resource(base_url, obs, credentials, args.region)
        print(f"  [Observation] {len(p['observations'])} loaded")

        for enc in encounter_resources(p):
            post_resource(base_url, enc, credentials, args.region)
        print(f"  [Encounter] {len(p['encounters'])} loaded")

        for med in medication_request_resources(p):
            post_resource(base_url, med, credentials, args.region)
        print(f"  [MedicationRequest] {len(p['medications'])} loaded")

    print(f"\nDone. Loaded {len(PATIENTS)} patients with clinical history into {args.datastore_id}.")


if __name__ == "__main__":
    main()
