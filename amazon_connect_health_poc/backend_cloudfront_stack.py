from aws_cdk import (
    Duration,
    Stack,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
)
from constructs import Construct


class BackendCloudFrontStack(Stack):
    """HTTPS proxy in front of the backend ALB.

    Port of backend/infrastructure/cloudfront-proxy-stack.yaml.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        alb_dns_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        origin = origins.HttpOrigin(
            alb_dns_name,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
            origin_ssl_protocols=[cloudfront.OriginSslPolicy.TLS_V1_2],
            read_timeout=Duration.seconds(60),
        )

        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            comment="HTTPS proxy for Patient Insights Backend",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                compress=True,
            ),
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
        )
        # The L2 Distribution silently drops minimum_protocol_version when using the
        # CloudFront default certificate (no custom domain). The source template pins
        # TLSv1.2_2021 even on the default cert, which IS valid in raw CloudFormation
        # -- restore it via an L1 escape hatch.
        self.distribution.node.default_child.add_property_override(
            "DistributionConfig.ViewerCertificate",
            {"CloudFrontDefaultCertificate": True, "MinimumProtocolVersion": "TLSv1.2_2021"},
        )

        self.backend_url = f"https://{self.distribution.distribution_domain_name}"
