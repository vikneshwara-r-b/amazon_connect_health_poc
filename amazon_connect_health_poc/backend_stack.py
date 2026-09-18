from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    aws_cognito as cognito,
    aws_ec2 as ec2,
    aws_ecr_assets as ecr_assets,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
)
from constructs import Construct

from .cloudfront_prefix_lists import cloudfront_prefix_list_id

CONTAINER_PORT = 5000


class BackendStack(Stack):
    """Patient Insights backend: ECS Fargate (Python Flask) behind an ALB.

    Port of backend/infrastructure/cloudformation.yaml. The Docker image is built
    and pushed by CDK itself via DockerImageAsset, replacing the CodeBuild/S3-zip
    pipeline from the source template.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.IVpc,
        environment: str = "dev",
        healthlake_datastore_id: str,
        domain_id: str,
        # No "runtime." prefix -- botocore adds it automatically via a hostPrefix
        # trait on StartPatientInsightsJob/GetPatientInsightsJob; including it here
        # too doubles it and breaks DNS resolution (see backend/config.py).
        service_endpoint: str = "https://health-agent.us-east-1.api.aws",
        cors_origin: str = "*",
        user_pool: cognito.IUserPool | None = None,
        user_pool_client: cognito.IUserPoolClient | None = None,
        use_cloudfront: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Output bucket for Patient Insights + streaming output. The source template
        # can optionally accept an existing bucket name; a from-scratch CDK app has no
        # reason to support that, so this always creates one.
        self.output_bucket = s3.Bucket(
            self,
            "OutputBucket",
            bucket_name=f"connect-health-output-{self.account}-{environment}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        cluster = ecs.Cluster(
            self,
            "Cluster",
            cluster_name=f"patient-insights-backend-{environment}",
            vpc=vpc,
            container_insights_v2=ecs.ContainerInsights.ENABLED,
        )

        log_group = logs.LogGroup(
            self,
            "LogGroup",
            log_group_name=f"/ecs/patient-insights-backend-{environment}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        task_role = iam.Role(
            self,
            "TaskRole",
            role_name=f"patient-insights-backend-task-{environment}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "healthlake:ReadResource",
                    "healthlake:SearchWithGet",
                    "healthlake:SearchWithPost",
                    "healthlake:SearchEverything",
                    "healthlake:GetCapabilities",
                    # Write access for Encounter (session start) and DocumentReference
                    # (approved SOAP notes) — HealthLake has no finer-grained ARN scoping
                    # than the datastore itself, so this can't be limited to those two
                    # resource types.
                    "healthlake:CreateResource",
                    "healthlake:UpdateResource",
                ],
                resources=[
                    f"arn:aws:healthlake:{self.region}:{self.account}:datastore/fhir/{healthlake_datastore_id}"
                ],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                # ARN formats not yet published for this preview service — Resource '*'
                # matches the source template's scoping.
                actions=[
                    "health-agent:StartPatientInsightsJob",
                    "health-agent:GetPatientInsightsJob",
                    "health-agent:GenerateMedicalCodes",
                ],
                resources=["*"],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
                resources=[self.output_bucket.bucket_arn, f"{self.output_bucket.bucket_arn}/*"],
            )
        )
        task_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                    "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-5-20250929-v1:0",
                    f"arn:aws:bedrock:us-east-1:{self.account}:inference-profile/us.anthropic.claude-sonnet-4-5-20250929-v1:0",
                ],
            )
        )

        alb_security_group = ec2.SecurityGroup(
            self,
            "AlbSecurityGroup",
            vpc=vpc,
            description="Security group for Patient Insights Backend ALB",
            allow_all_outbound=True,
        )
        if use_cloudfront:
            alb_security_group.add_ingress_rule(
                ec2.Peer.prefix_list(cloudfront_prefix_list_id(self.region)),
                ec2.Port.tcp(80),
                "Allow HTTP from CloudFront managed prefix list only",
            )
        else:
            # Bypass mode: nothing fronts this ALB, so the browser hits it
            # directly. No TLS, no CloudFront-only restriction -- fine for
            # temporary sandbox testing, not for production.
            alb_security_group.add_ingress_rule(
                ec2.Peer.any_ipv4(),
                ec2.Port.tcp(80),
                "Allow HTTP from the internet (CloudFront bypass mode)",
            )

        ecs_security_group = ec2.SecurityGroup(
            self,
            "EcsSecurityGroup",
            vpc=vpc,
            description="Security group for Patient Insights Backend ECS tasks",
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
            load_balancer_name=f"patient-insights-{environment}",
        )
        alb.set_attribute("routing.http.drop_invalid_header_fields.enabled", "true")

        # Pin to amd64: Fargate tasks here run X86_64 (the default RuntimePlatform,
        # not overridden below), and local builds on Apple Silicon otherwise default
        # to arm64 -- some base images (e.g. eclipse-temurin's alpine tags used by
        # the streaming service) don't publish an arm64 manifest at all.
        image_asset = ecr_assets.DockerImageAsset(
            self, "BackendImage", directory="backend", platform=ecr_assets.Platform.LINUX_AMD64
        )

        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "Service",
            service_name=f"patient-insights-backend-{environment}",
            cluster=cluster,
            cpu=256,
            memory_limit_mib=512,
            desired_count=1,
            min_healthy_percent=100,
            max_healthy_percent=200,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            assign_public_ip=True,
            load_balancer=alb,
            open_listener=False,
            listener_port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            security_groups=[ecs_security_group],
            public_load_balancer=True,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_docker_image_asset(image_asset),
                container_name="patient-insights-backend",
                container_port=CONTAINER_PORT,
                task_role=task_role,
                log_driver=ecs.LogDrivers.aws_logs(stream_prefix="backend", log_group=log_group),
                environment={
                    "AWS_REGION": self.region,
                    "DOMAIN_ID": domain_id,
                    "HEALTHLAKE_DATASTORE_ID": healthlake_datastore_id,
                    "SERVICE_ENDPOINT": service_endpoint,
                    "S3_OUTPUT_BUCKET": f"s3://{self.output_bucket.bucket_name}/insights-output/",
                    "STREAMING_OUTPUT_BUCKET": self.output_bucket.bucket_name,
                    "SERVER_PORT": str(CONTAINER_PORT),
                    "SERVER_HOST": "0.0.0.0",
                    "DEBUG": "false",
                    "COGNITO_USER_POOL_ID": user_pool.user_pool_id if user_pool else "",
                    "COGNITO_CLIENT_ID": user_pool_client.user_pool_client_id
                    if user_pool_client
                    else "",
                    "CORS_ORIGINS": cors_origin,
                },
            ),
        )
        service.target_group.configure_health_check(
            path="/api/health",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
        )

        self.alb_dns_name = alb.load_balancer_dns_name
