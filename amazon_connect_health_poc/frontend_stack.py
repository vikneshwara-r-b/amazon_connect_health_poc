from pathlib import Path

from aws_cdk import (
    RemovalPolicy,
    Stack,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment,
)
from constructs import Construct

CONFIG_JS_KEY = "js/config.js"
CONFIG_JS_PATH = Path(__file__).parent.parent / "frontend" / CONFIG_JS_KEY

# Exact substrings from frontend/js/config.js that get swapped for real deploy-time
# values. Kept as plain string replacement (not a templating engine) so the file
# stays a normal, directly-runnable JS file for local development.
WSS_PLACEHOLDER = "wss://<YOUR_WSS_CLOUDFRONT>.cloudfront.net/stream"
BACKEND_PLACEHOLDER = "https://<YOUR_BACKEND_CLOUDFRONT>.cloudfront.net"
USER_POOL_ID_PLACEHOLDER = "'YOUR_COGNITO_USER_POOL_ID'"
CLIENT_ID_PLACEHOLDER = "'YOUR_COGNITO_CLIENT_ID'"


def _render_config_js(
    *,
    backend_url: str,
    websocket_url: str,
    user_pool_id: str | None,
    user_pool_client_id: str | None,
) -> str:
    """Bake the deploy-time backend/WSS URLs (and optional Cognito IDs) into
    config.js, matching what DEPLOYMENT_GUIDE.md Step 3b does by hand.

    backend_url/websocket_url may contain unresolved CDK tokens (the CloudFront
    domain names aren't known until deploy) -- that's fine, since BucketDeployment's
    Source.data resolves tokens in its `data` argument at deploy time before
    writing the file to S3.
    """
    content = CONFIG_JS_PATH.read_text()

    replacements = {
        WSS_PLACEHOLDER: websocket_url,
        BACKEND_PLACEHOLDER: backend_url,
        USER_POOL_ID_PLACEHOLDER: f"'{user_pool_id}'" if user_pool_id else USER_POOL_ID_PLACEHOLDER,
        CLIENT_ID_PLACEHOLDER: f"'{user_pool_client_id}'"
        if user_pool_client_id
        else CLIENT_ID_PLACEHOLDER,
    }
    for placeholder, value in replacements.items():
        if placeholder not in content:
            raise ValueError(
                f"Expected placeholder {placeholder!r} not found in {CONFIG_JS_PATH}. "
                "Has the file's format changed? Update the substitution logic in "
                "frontend_stack.py to match."
            )
        content = content.replace(placeholder, value)

    return content


class FrontendStack(Stack):
    """Frontend static site.

    Port of streaming-service/infrastructure/cloudfront-stack.yaml. Also folds in
    what the deployment guide does by hand afterwards (`aws s3 sync` + cache
    invalidation, and manually editing config.js) via BucketDeployment, so
    `cdk deploy` alone publishes a working site.

    use_cloudfront controls two independent-but-linked deployment modes:
      True  (default): private S3 bucket behind CloudFront + OAC, matching the
             source template exactly.
      False: public S3 static website hosting, no CloudFront at all -- for
             accounts where CloudFront is blocked (e.g. pending AWS account
             verification for new/low-usage accounts). No TLS in this mode:
             S3 website endpoints are HTTP-only by design.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        frontend_bucket_name: str,
        backend_url: str,
        websocket_url: str,
        user_pool_id: str | None = None,
        user_pool_client_id: str | None = None,
        use_cloudfront: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.distribution = None

        if use_cloudfront:
            bucket = s3.Bucket(
                self,
                "FrontendBucket",
                bucket_name=frontend_bucket_name,
                encryption=s3.BucketEncryption.S3_MANAGED,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
                enforce_ssl=True,
                removal_policy=RemovalPolicy.DESTROY,
                auto_delete_objects=True,
            )

            self.distribution = cloudfront.Distribution(
                self,
                "Distribution",
                default_root_object="index.html",
                default_behavior=cloudfront.BehaviorOptions(
                    origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                    cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
                    cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                    compress=True,
                ),
                price_class=cloudfront.PriceClass.PRICE_CLASS_100,
                minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            )
            # The L2 Distribution silently drops minimum_protocol_version when using
            # the CloudFront default certificate (no custom domain). The source
            # template pins TLSv1.2_2021 even on the default cert, which IS valid in
            # raw CloudFormation -- restore it via an L1 escape hatch.
            self.distribution.node.default_child.add_property_override(
                "DistributionConfig.ViewerCertificate",
                {"CloudFrontDefaultCertificate": True, "MinimumProtocolVersion": "TLSv1.2_2021"},
            )
            deployment_kwargs = {"distribution": self.distribution, "distribution_paths": ["/*"]}
            self.site_url = f"https://{self.distribution.distribution_domain_name}"
        else:
            # S3 static website hosting: public-read bucket, no CloudFront/OAC.
            # public_read_access=True requires an explicit block_public_access that
            # still permits a public bucket policy (confirmed via a synth error
            # otherwise: "Cannot use 'publicReadAccess' property... without
            # allowing bucket-level public access").
            bucket = s3.Bucket(
                self,
                "FrontendBucket",
                bucket_name=frontend_bucket_name,
                encryption=s3.BucketEncryption.S3_MANAGED,
                public_read_access=True,
                block_public_access=s3.BlockPublicAccess(
                    block_public_acls=True,
                    block_public_policy=False,
                    ignore_public_acls=True,
                    restrict_public_buckets=False,
                ),
                website_index_document="index.html",
                website_error_document="index.html",
                # S3 website endpoints are HTTP-only -- enforce_ssl=True would deny
                # every request against this endpoint.
                enforce_ssl=False,
                removal_policy=RemovalPolicy.DESTROY,
                auto_delete_objects=True,
            )
            deployment_kwargs = {}
            self.site_url = bucket.bucket_website_url

        rendered_config_js = _render_config_js(
            backend_url=backend_url,
            websocket_url=websocket_url,
            user_pool_id=user_pool_id,
            user_pool_client_id=user_pool_client_id,
        )

        s3_deployment.BucketDeployment(
            self,
            "DeployFrontend",
            sources=[
                s3_deployment.Source.asset("frontend", exclude=[CONFIG_JS_KEY]),
                s3_deployment.Source.data(CONFIG_JS_KEY, rendered_config_js),
            ],
            destination_bucket=bucket,
            **deployment_kwargs,
        )
