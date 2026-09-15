#!/usr/bin/env python3
import os

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2

from amazon_connect_health_poc.backend_cloudfront_stack import BackendCloudFrontStack
from amazon_connect_health_poc.backend_stack import BackendStack
from amazon_connect_health_poc.cognito_stack import CognitoStack
from amazon_connect_health_poc.connect_health_resources_stack import (
    ConnectHealthResourcesStack,
)
from amazon_connect_health_poc.frontend_stack import FrontendStack
from amazon_connect_health_poc.streaming_cloudfront_stack import StreamingCloudFrontStack
from amazon_connect_health_poc.streaming_stack import StreamingStack


def get_context(app: cdk.App, key: str, default: str = "") -> str:
    """Read a value from -c context, falling back to an env var of the same
    name (upper-cased), then to `default`. Lets deploys be driven either by
    `cdk deploy -c domainId=dom-abc123 ...` or exported env vars.

    An empty-string context value (e.g. a placeholder left blank in cdk.json)
    is treated the same as unset, so a computed `default` still applies --
    otherwise a blank cdk.json entry silently wins over a meaningful default
    (confirmed this bit AmazonConnectHealthFrontend's bucket name: an empty
    frontendBucketName in cdk.json rendered as BucketName: "" rather than
    falling back to the computed name)."""
    value = app.node.try_get_context(key)
    if value not in (None, ""):
        return value
    return os.environ.get(key, default)


app = cdk.App()

env = cdk.Environment(
    account=os.getenv("CDK_DEFAULT_ACCOUNT"),
    region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"),
)

environment_name = get_context(app, "environment", "dev")
connect_health_domain_name = get_context(app, "connectHealthDomainName", "connect-health-demo")
existing_domain_id = get_context(app, "existingDomainId") or None
existing_subscription_id = get_context(app, "existingSubscriptionId") or None
healthlake_datastore_name = get_context(app, "healthlakeDatastoreName", "connect-health-demo")
existing_healthlake_datastore_id = get_context(app, "existingHealthlakeDatastoreId") or None
cors_origin = get_context(app, "corsOrigin", "*")
streaming_certificate_arn = get_context(app, "streamingCertificateArn") or None
frontend_bucket_name = get_context(
    # Account-scoped, matching OutputBucket/SourceBucket's naming convention
    # elsewhere in this app -- S3 bucket names are globally unique, and the
    # source DEPLOYMENT_GUIDE.sample.md explicitly warns to pick a unique name
    # for this exact bucket.
    app,
    "frontendBucketName",
    f"connect-health-frontend-{env.account}-{environment_name}",
)
demo_user_email = get_context(app, "demoUserEmail", "connecthealth_demo@example.com")
demo_user_password = get_context(app, "demoUserPassword") or None
enable_cognito = get_context(app, "enableCognito", "true").lower() == "true"
use_cloudfront = get_context(app, "useCloudFront", "true").lower() == "true"

# A single Vpc.from_lookup call, shared by both service stacks, so synth doesn't
# do the default-VPC context lookup twice for the same account/region.
network_stack = cdk.Stack(app, "AmazonConnectHealthNetwork", env=env)
vpc = ec2.Vpc.from_lookup(network_stack, "DefaultVpc", is_default=True)

prereqs_stack = ConnectHealthResourcesStack(
    app,
    "AmazonConnectHealthPrereqs",
    env=env,
    connect_health_domain_name=connect_health_domain_name,
    existing_domain_id=existing_domain_id,
    existing_subscription_id=existing_subscription_id,
    healthlake_datastore_name=healthlake_datastore_name,
    existing_healthlake_datastore_id=existing_healthlake_datastore_id,
)

cognito_stack = None
if enable_cognito:
    cognito_stack = CognitoStack(
        app,
        "AmazonConnectHealthCognito",
        env=env,
        environment=environment_name,
        demo_user_email=demo_user_email,
        demo_user_password=demo_user_password,
    )

backend_stack = BackendStack(
    app,
    "AmazonConnectHealthBackend",
    env=env,
    vpc=vpc,
    environment=environment_name,
    healthlake_datastore_id=prereqs_stack.healthlake_datastore_id,
    domain_id=prereqs_stack.domain_id,
    cors_origin=cors_origin,
    user_pool=cognito_stack.user_pool if cognito_stack else None,
    user_pool_client=cognito_stack.user_pool_client if cognito_stack else None,
    use_cloudfront=use_cloudfront,
)
backend_stack.add_stack_dependency(network_stack)
backend_stack.add_stack_dependency(prereqs_stack)
if cognito_stack:
    backend_stack.add_stack_dependency(cognito_stack)

backend_cloudfront_stack = None
if use_cloudfront:
    backend_cloudfront_stack = BackendCloudFrontStack(
        app,
        "AmazonConnectHealthBackendCloudFront",
        env=env,
        alb_dns_name=backend_stack.alb_dns_name,
    )
    backend_cloudfront_stack.add_stack_dependency(backend_stack)

streaming_stack = StreamingStack(
    app,
    "AmazonConnectHealthStreaming",
    env=env,
    vpc=vpc,
    environment=environment_name,
    output_bucket_uri=f"s3://{backend_stack.output_bucket.bucket_name}",
    domain_id=prereqs_stack.domain_id,
    subscription_id=prereqs_stack.subscription_id,
    certificate_arn=streaming_certificate_arn,
    use_cloudfront=use_cloudfront,
)
streaming_stack.add_stack_dependency(network_stack)
streaming_stack.add_stack_dependency(prereqs_stack)
streaming_stack.add_stack_dependency(backend_stack)

streaming_cloudfront_stack = None
if use_cloudfront:
    streaming_cloudfront_stack = StreamingCloudFrontStack(
        app,
        "AmazonConnectHealthStreamingCloudFront",
        env=env,
        alb_dns_name=streaming_stack.alb_dns_name,
    )
    streaming_cloudfront_stack.add_stack_dependency(streaming_stack)

if use_cloudfront:
    backend_url = backend_cloudfront_stack.backend_url
    websocket_url = streaming_cloudfront_stack.websocket_url
else:
    # CloudFront bypass: talk to the ALBs directly. No TLS in this mode -- S3
    # website endpoints and these ALBs are both plain HTTP/WS. Fine for
    # temporary sandbox testing (e.g. while an account awaits AWS's CloudFront
    # verification), not for anything shared beyond that.
    backend_url = f"http://{backend_stack.alb_dns_name}"
    websocket_url = f"ws://{streaming_stack.alb_dns_name}/stream"

frontend_stack = FrontendStack(
    app,
    "AmazonConnectHealthFrontend",
    env=env,
    frontend_bucket_name=frontend_bucket_name,
    backend_url=backend_url,
    websocket_url=websocket_url,
    user_pool_id=cognito_stack.user_pool.user_pool_id if cognito_stack else None,
    user_pool_client_id=cognito_stack.user_pool_client.user_pool_client_id
    if cognito_stack
    else None,
    use_cloudfront=use_cloudfront,
)
if use_cloudfront:
    frontend_stack.add_stack_dependency(backend_cloudfront_stack)
    frontend_stack.add_stack_dependency(streaming_cloudfront_stack)
else:
    frontend_stack.add_stack_dependency(backend_stack)
    frontend_stack.add_stack_dependency(streaming_stack)

app.synth()
