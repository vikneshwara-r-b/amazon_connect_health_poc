from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_certificatemanager as acm,
    aws_ec2 as ec2,
    aws_ecr_assets as ecr_assets,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_logs as logs,
)
from constructs import Construct

from .cloudfront_prefix_lists import cloudfront_prefix_list_id

CONTAINER_PORT = 8081


def _bucket_name_from_uri(output_bucket_uri: str) -> str:
    """Extract the bucket name from an 's3://bucket' URI, mirroring the source
    template's !Select [1, !Split ["//", ...]] intrinsic."""
    return output_bucket_uri.split("//", 1)[1]


class StreamingStack(Stack):
    """ConnectHealth streaming (ambient documentation) service: ECS Fargate
    (Java WebSocket server) behind an ALB.

    Port of streaming-service/infrastructure/cloudformation.yaml.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        environment: str = "dev",
        output_bucket_uri: str,
        domain_id: str = "",
        subscription_id: str = "",
        streaming_endpoint: str = "https://streaming.health-agent.us-east-1.api.aws",
        certificate_arn: str | None = None,
        use_cloudfront: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bucket_name = _bucket_name_from_uri(output_bucket_uri)

        cluster = ecs.Cluster(
            self,
            "Cluster",
            cluster_name=f"connect-health-streaming-{environment}",
            vpc=vpc,
            container_insights_v2=ecs.ContainerInsights.ENABLED,
        )

        log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name=f"/ecs/connect-health-streaming-{environment}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        task_role = iam.Role(
            self,
            "TaskRole",
            role_name=f"connect-health-streaming-task-{environment}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                # ARN format not yet published for this preview service — Resource '*'
                # matches the source template's scoping.
                actions=["health-agent:StartMedicalScribeListeningSession"],
                resources=["*"],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
                resources=[
                    f"arn:aws:s3:::{bucket_name}",
                    f"arn:aws:s3:::{bucket_name}/*",
                ],
            )
        )

        alb_security_group = ec2.SecurityGroup(
            self,
            "AlbSecurityGroup",
            vpc=vpc,
            description="Security group for ConnectHealth Streaming ALB",
            allow_all_outbound=True,
        )
        if use_cloudfront:
            # Only port 80 — CloudFront terminates TLS and forwards HTTP to the ALB.
            # Adding a port 443 rule would exceed the default 60-rules-per-SG quota,
            # since the CloudFront prefix list contains ~45 IP ranges (each a rule).
            alb_security_group.add_ingress_rule(
                ec2.Peer.prefix_list(cloudfront_prefix_list_id(self.region)),
                ec2.Port.tcp(80),
                "Allow HTTP from CloudFront managed prefix list only",
            )
        else:
            # Bypass mode: nothing fronts this ALB, so the browser connects
            # directly (ws://, not wss://). No TLS, no CloudFront-only
            # restriction -- fine for temporary sandbox testing, not production.
            alb_security_group.add_ingress_rule(
                ec2.Peer.any_ipv4(),
                ec2.Port.tcp(80),
                "Allow HTTP from the internet (CloudFront bypass mode)",
            )

        ecs_security_group = ec2.SecurityGroup(
            self,
            "EcsSecurityGroup",
            vpc=vpc,
            description="Security group for ConnectHealth Streaming ECS tasks",
            allow_all_outbound=True,
        )
        ecs_security_group.add_ingress_rule(
            ec2.Peer.security_group_id(alb_security_group.security_group_id),
            ec2.Port.tcp(CONTAINER_PORT),
            "Allow inbound from ALB only",
        )

        alb = elbv2.ApplicationLoadBalancer(
            self,
            "Alb",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_security_group,
            load_balancer_name=f"connect-health-streaming-{environment}",
        )
        alb.set_attribute("routing.http.drop_invalid_header_fields.enabled", "true")

        # Pin to amd64: Fargate tasks here run X86_64 (the default RuntimePlatform,
        # not overridden below), and local builds on Apple Silicon otherwise default
        # to arm64 -- eclipse-temurin's alpine-based tags used in this Dockerfile
        # don't publish an arm64 manifest, so an unpinned build fails outright.
        image_asset = ecr_assets.DockerImageAsset(
            self,
            "StreamingImage",
            directory="streaming-service",
            platform=ecr_assets.Platform.LINUX_AMD64,
        )

        # CertificateArn is optional in the source template: with one, the HTTP
        # listener (80) redirects to HTTPS (443); without, HTTP forwards directly.
        listener_kwargs = {}
        if certificate_arn:
            certificate = acm.Certificate.from_certificate_arn(self, "Certificate", certificate_arn)
            listener_kwargs.update(
                protocol=elbv2.ApplicationProtocol.HTTPS,
                certificate=certificate,
                ssl_policy=elbv2.SslPolicy.TLS13_12,
                redirect_http=True,
            )
        else:
            listener_kwargs.update(protocol=elbv2.ApplicationProtocol.HTTP)

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "Service",
            service_name=f"connect-health-streaming-{environment}",
            cluster=cluster,
            cpu=512,
            memory_limit_mib=1024,
            desired_count=1,
            min_healthy_percent=100,
            max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            assign_public_ip=True,
            load_balancer=alb,
            open_listener=False,
            security_groups=[ecs_security_group],
            public_load_balancer=True,
            **listener_kwargs,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_docker_image_asset(image_asset),
                container_name="connect-health-streaming",
                container_port=CONTAINER_PORT,
                task_role=task_role,
                log_driver=ecs.LogDrivers.aws_logs(stream_prefix="streaming", log_group=log_group),
                environment={
                    "CONNECT_HEALTH_REGION": self.region,
                    "OUTPUT_BUCKET": output_bucket_uri,
                    "DOMAIN_ID": domain_id,
                    "SUBSCRIPTION_ID": subscription_id,
                    "PORT": str(CONTAINER_PORT),
                    "STREAMING_ENDPOINT": streaming_endpoint,
                },
            ),
        )
        service.target_group.configure_health_check(
            path="/",
            protocol=elbv2.Protocol.HTTP,
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
        )
        service.target_group.enable_cookie_stickiness(Duration.seconds(86400))

        self.alb_dns_name = alb.load_balancer_dns_name
