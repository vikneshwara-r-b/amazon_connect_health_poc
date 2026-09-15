#!/usr/bin/env python3
"""One-off utility: deletes every FHIR resource from a HealthLake R4 datastore
via the FHIR REST API (search each resource type's pages, DELETE each hit),
signed the same way load_sample_healthlake_data.py signs its requests.

HealthLake has no bulk-delete or "empty datastore" operation -- the only way
to clear one out without deleting/recreating the datastore itself (which
would change its ID and require redeploying the backend stack) is to search
and delete every resource one at a time.

Usage:
    python3 purge_healthlake_data.py --datastore-id <id> [--profile NAME] [--region us-east-1]
"""
import argparse
import sys

import boto3
import requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# Order matters: resources that reference a Patient must be deleted before
# the Patient itself, or HealthLake will reject the Patient delete.
RESOURCE_TYPES = ["MedicationRequest", "Encounter", "Observation", "Condition", "Patient"]


def signed_request(method, url, credentials, region):
    headers = {"Accept": "application/fhir+json"}
    request = AWSRequest(method=method, url=url, headers=headers)
    SigV4Auth(credentials, "healthlake", region).add_auth(request)
    fn = requests.get if method == "GET" else requests.delete
    return fn(url, headers=dict(request.headers), timeout=30)


def iter_resource_ids(base_url, resource_type, credentials, region):
    url = f"{base_url}{resource_type}?_count=100"
    while url:
        resp = signed_request("GET", url, credentials, region)
        resp.raise_for_status()
        bundle = resp.json()
        for entry in bundle.get("entry", []):
            yield entry["resource"]["id"]
        next_link = next((l["url"] for l in bundle.get("link", []) if l["relation"] == "next"), None)
        url = next_link


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datastore-id", required=True)
    parser.add_argument("--profile", default=None)
    parser.add_argument("--region", default="us-east-1")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile) if args.profile else boto3.Session()
    credentials = session.get_credentials()
    base_url = f"https://healthlake.{args.region}.amazonaws.com/datastore/{args.datastore_id}/r4/"

    total_deleted = 0
    for resource_type in RESOURCE_TYPES:
        ids = list(iter_resource_ids(base_url, resource_type, credentials, args.region))
        for rid in ids:
            resp = signed_request("DELETE", f"{base_url}{resource_type}/{rid}", credentials, args.region)
            resp.raise_for_status()
        print(f"[{resource_type}] {len(ids)} deleted")
        total_deleted += len(ids)

    print(f"\nDone. Deleted {total_deleted} resources from {args.datastore_id}.")


if __name__ == "__main__":
    main()
