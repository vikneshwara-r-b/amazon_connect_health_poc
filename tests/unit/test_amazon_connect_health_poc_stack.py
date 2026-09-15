import aws_cdk as cdk
import aws_cdk.assertions as assertions
from aws_cdk import aws_ec2 as ec2

from amazon_connect_health_poc.backend_stack import BackendStack
from amazon_connect_health_poc.connect_health_resources_stack import (
    ConnectHealthResourcesStack,
)
from amazon_connect_health_poc.frontend_stack import FrontendStack
from amazon_connect_health_poc.streaming_stack import StreamingStack

ENV = cdk.Environment(account="123456789012", region="us-east-1")


def _vpc(scope: cdk.Stack) -> ec2.IVpc:
    return ec2.Vpc(scope, "TestVpc", max_azs=2)


def test_backend_task_definition_container_port():
    app = cdk.App()
    net = cdk.Stack(app, "Net", env=ENV)
    vpc = _vpc(net)
    stack = BackendStack(
        app,
        "Backend",
        env=ENV,
        vpc=vpc,
        healthlake_datastore_id="fake-datastore-id",
        domain_id="dom-fake",
    )
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties(
        "AWS::ECS::TaskDefinition",
        {
            "ContainerDefinitions": assertions.Match.array_with(
                [assertions.Match.object_like({"PortMappings": [{"ContainerPort": 5000, "Protocol": "tcp"}]})]
            )
        },
    )


def test_backend_output_bucket_denies_insecure_transport():
    app = cdk.App()
    net = cdk.Stack(app, "Net", env=ENV)
    vpc = _vpc(net)
    stack = BackendStack(
        app,
        "Backend",
        env=ENV,
        vpc=vpc,
        healthlake_datastore_id="fake-datastore-id",
        domain_id="dom-fake",
    )
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )
    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": assertions.Match.object_like(
                {
                    "Statement": assertions.Match.array_with(
                        [
                            assertions.Match.object_like(
                                {
                                    "Effect": "Deny",
                                    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                                }
                            )
                        ]
                    )
                }
            )
        },
    )


def test_backend_alb_security_group_restricted_to_cloudfront_prefix_list():
    app = cdk.App()
    net = cdk.Stack(app, "Net", env=ENV)
    vpc = _vpc(net)
    stack = BackendStack(
        app,
        "Backend",
        env=ENV,
        vpc=vpc,
        healthlake_datastore_id="fake-datastore-id",
        domain_id="dom-fake",
    )
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties(
        "AWS::EC2::SecurityGroupIngress",
        {
            "IpProtocol": "tcp",
            "FromPort": 80,
            "ToPort": 80,
            "SourcePrefixListId": "pl-3b927c52",
        },
    )
    # No security group should allow unrestricted internet ingress.
    template.resource_count_is("AWS::EC2::SecurityGroupIngress", 2)
    for sg_ingress in template.find_resources("AWS::EC2::SecurityGroupIngress").values():
        props = sg_ingress["Properties"]
        assert props.get("CidrIp") != "0.0.0.0/0"


def test_streaming_target_group_has_websocket_stickiness():
    app = cdk.App()
    net = cdk.Stack(app, "Net", env=ENV)
    vpc = _vpc(net)
    stack = StreamingStack(
        app,
        "Streaming",
        env=ENV,
        vpc=vpc,
        output_bucket_uri="s3://fake-output-bucket",
        domain_id="dom-fake",
        subscription_id="sub-fake",
    )
    template = assertions.Template.from_stack(stack)

    # The target group's own Port is just a registration default for TargetType=ip;
    # the actual routing port comes from the ECS Service's LoadBalancers config.
    template.has_resource_properties(
        "AWS::ElasticLoadBalancingV2::TargetGroup",
        {
            "TargetGroupAttributes": assertions.Match.array_with(
                [
                    assertions.Match.object_like(
                        {"Key": "stickiness.enabled", "Value": "true"}
                    )
                ]
            ),
        },
    )
    template.has_resource_properties(
        "AWS::ECS::Service",
        {
            "LoadBalancers": [
                assertions.Match.object_like({"ContainerPort": 8081})
            ]
        },
    )


def test_prereqs_creates_healthlake_datastore_when_no_existing_id_given():
    app = cdk.App()
    stack = ConnectHealthResourcesStack(app, "Prereqs", env=ENV)
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties(
        "AWS::HealthLake::FHIRDatastore",
        {"DatastoreTypeVersion": "R4", "DatastoreName": "connect-health-demo"},
    )
    template.resource_count_is("AWS::CloudFormation::CustomResource", 2)


def test_prereqs_skips_creation_when_existing_ids_given():
    app = cdk.App()
    stack = ConnectHealthResourcesStack(
        app,
        "Prereqs",
        env=ENV,
        existing_domain_id="dom-existing123",
        existing_subscription_id="sub-existing456",
        existing_healthlake_datastore_id="ds-existing789",
    )
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::HealthLake::FHIRDatastore", 0)
    template.resource_count_is("AWS::CloudFormation::CustomResource", 0)
    template.resource_count_is("AWS::Lambda::Function", 0)

    assert stack.healthlake_datastore_id == "ds-existing789"
    assert stack.domain_id == "dom-existing123"
    assert stack.subscription_id == "sub-existing456"


def _frontend_kwargs(**overrides):
    kwargs = dict(
        frontend_bucket_name="connect-health-frontend-123456789012-dev",
        backend_url="https://backend.example.com",
        websocket_url="wss://streaming.example.com/stream",
    )
    kwargs.update(overrides)
    return kwargs


def test_frontend_cloudfront_mode_uses_private_bucket_and_distribution():
    app = cdk.App()
    stack = FrontendStack(app, "Frontend", env=ENV, **_frontend_kwargs())
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::CloudFront::Distribution", 1)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )
    # auto_delete_objects=True and enforce_ssl=True both add BucketPolicy
    # statements referencing Principal "*" (a deny-non-HTTPS statement) even on
    # a private bucket -- confirm specifically that nothing *allows* public
    # s3:GetObject, which is the actual public-read-access signal.
    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": assertions.Match.object_like(
                {
                    "Statement": assertions.Match.not_(
                        assertions.Match.array_with(
                            [
                                assertions.Match.object_like(
                                    {
                                        "Effect": "Allow",
                                        "Action": "s3:GetObject",
                                        "Principal": {"AWS": "*"},
                                    }
                                )
                            ]
                        )
                    )
                }
            )
        },
    )


def test_frontend_website_mode_uses_public_bucket_with_no_cloudfront():
    app = cdk.App()
    stack = FrontendStack(
        app, "Frontend", env=ENV, use_cloudfront=False, **_frontend_kwargs()
    )
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::CloudFront::Distribution", 0)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "WebsiteConfiguration": {
                "IndexDocument": "index.html",
                "ErrorDocument": "index.html",
            }
        },
    )
    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": assertions.Match.object_like(
                {
                    "Statement": assertions.Match.array_with(
                        [
                            assertions.Match.object_like(
                                {
                                    "Effect": "Allow",
                                    "Action": "s3:GetObject",
                                    "Principal": {"AWS": "*"},
                                }
                            )
                        ]
                    )
                }
            )
        },
    )
