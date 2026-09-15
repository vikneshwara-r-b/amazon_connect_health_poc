"""CloudFront managed origin-facing prefix list IDs, by region.

Used to restrict ALB security groups to CloudFront-only ingress. Mirrors the
CloudFrontPrefixListMap Mapping in the source CloudFormation templates.
"""

CLOUDFRONT_ORIGIN_FACING_PREFIX_LIST_IDS = {
    "us-east-1": "pl-3b927c52",
    "us-east-2": "pl-b6a144df",
    "us-west-1": "pl-4ea04527",
    "us-west-2": "pl-82a045eb",
}


def cloudfront_prefix_list_id(region: str) -> str:
    try:
        return CLOUDFRONT_ORIGIN_FACING_PREFIX_LIST_IDS[region]
    except KeyError as exc:
        raise ValueError(
            f"No CloudFront origin-facing prefix list ID known for region '{region}'. "
            "Add it to CLOUDFRONT_ORIGIN_FACING_PREFIX_LIST_IDS or deploy to a supported region "
            f"({', '.join(CLOUDFRONT_ORIGIN_FACING_PREFIX_LIST_IDS)})."
        ) from exc
