from aws_cdk import (
    Duration,
    Stack,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
)
from constructs import Construct


class StreamingCloudFrontStack(Stack):
    """WSS proxy in front of the streaming service ALB.

    Port of streaming-service/infrastructure/cloudfront-wss-stack.yaml.
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
            read_timeout=Duration.seconds(60),
            keepalive_timeout=Duration.seconds(60),
        )

        self.distribution = cloudfront.Distribution(
            self,
            "Distribution",
            comment="WebSocket Proxy (wss://)",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origin,
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.HTTPS_ONLY,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
                cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                compress=False,
            ),
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
        )
        # See BackendCloudFrontStack for why this override is needed alongside the
        # CloudFront default certificate.
        self.distribution.node.default_child.add_property_override(
            "DistributionConfig.ViewerCertificate",
            {"CloudFrontDefaultCertificate": True, "MinimumProtocolVersion": "TLSv1.2_2021"},
        )

        self.websocket_url = f"wss://{self.distribution.distribution_domain_name}/stream"
