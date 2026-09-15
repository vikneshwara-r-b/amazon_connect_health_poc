from aws_cdk import (
    CustomResource,
    Duration,
    Stack,
    aws_healthlake as healthlake,
    aws_iam as iam,
    aws_lambda as lambda_,
)
from constructs import Construct


class ConnectHealthResourcesStack(Stack):
    """Prerequisites from DEPLOYMENT_GUIDE.sample.md's "Prerequisites" section:
    a Connect Health Domain, a Subscription (required for streaming), and a
    HealthLake FHIR datastore.

    Each of the three can either be created here or passed through as an
    existing ID (set the corresponding `existing_*` prop) -- mirroring the
    source guide's "if you already have one, skip this step".

    HealthLake has a native CloudFormation resource (AWS::HealthLake::FHIRDatastore,
    aws_cdk.aws_healthlake.CfnFHIRDatastore), so that one is a plain CFN resource
    and CloudFormation itself waits for the datastore to reach ACTIVE.

    Amazon Connect Health has no CloudFormation resource type yet (confirmed: no
    AWS::ConnectHealth::* type, no aws_connecthealth CDK module -- it's a very new
    preview service). Domain and Subscription creation therefore go through
    Lambda-backed custom resources calling boto3's connecthealth client directly,
    same pattern as the demo-user custom resource in cognito_stack.py.

    CONFIRMED (via a real deploy's CloudWatch logs): the connecthealth boto3
    client uses lowerCamelCase member names throughout (name, domainId,
    subscriptionId, kmsKeyArn, webAppSetupConfiguration, tags) rather than the
    PascalCase convention most other boto3 clients use -- an initial PascalCase
    guess (Name, DomainId) failed parameter validation. The service model *is*
    present in the standard Lambda Python 3.12 runtime's bundled botocore, so
    that risk did not materialize.

    STILL UNCONFIRMED: create_domain's/create_subscription's response key
    names (domainId/subscriptionId) are inferred from the confirmed request-side
    casing, not yet directly observed -- each handler logs the full raw response
    before indexing into it, so a wrong guess here is visible in CloudWatch
    immediately rather than requiring another blind deploy-and-guess cycle.

    CONFIRMED (via a real AccessDeniedException): the IAM action/ARN service
    prefix for this service is `health-agent`, NOT `connecthealth` -- despite
    the boto3 SDK client id being 'connecthealth'. This matches the health-agent:*
    actions already granted in backend_stack.py/streaming_stack.py and the
    *.health-agent.*.api.aws service endpoints used elsewhere in this app. The
    AccessDenied error also revealed the real domain resource ARN format
    (arn:aws:health-agent:<region>:<account>:domain/<domainId>), now used to
    scope DomainResourceRole's policy instead of a wildcard.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        connect_health_domain_name: str = "connect-health-demo",
        existing_domain_id: str | None = None,
        existing_subscription_id: str | None = None,
        healthlake_datastore_name: str = "connect-health-demo",
        existing_healthlake_datastore_id: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- HealthLake FHIR datastore ---------------------------------------
        if existing_healthlake_datastore_id:
            self.healthlake_datastore_id = existing_healthlake_datastore_id
        else:
            datastore = healthlake.CfnFHIRDatastore(
                self,
                "Datastore",
                datastore_type_version="R4",
                datastore_name=healthlake_datastore_name,
            )
            self.healthlake_datastore_id = datastore.attr_datastore_id

        # --- Connect Health Domain --------------------------------------------
        if existing_domain_id:
            self.domain_id = existing_domain_id
        else:
            domain_role = iam.Role(
                self,
                "DomainResourceRole",
                assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "service-role/AWSLambdaBasicExecutionRole"
                    )
                ],
            )
            # Service prefix for IAM/ARN purposes is 'health-agent', not 'connecthealth'
            # (confirmed via a real AccessDeniedException -- see class docstring).
            domain_role.add_to_policy(
                iam.PolicyStatement(
                    actions=["health-agent:CreateDomain", "health-agent:DeleteDomain"],
                    resources=[f"arn:aws:health-agent:{self.region}:{self.account}:domain/*"],
                )
            )

            domain_function = lambda_.Function(
                self,
                "DomainResourceFunction",
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler="index.handler",
                timeout=Duration.seconds(60),
                role=domain_role,
                code=lambda_.Code.from_inline(
                    """
import boto3
import cfnresponse


def handler(event, context):
    client = boto3.client('connecthealth')
    request_type = event['RequestType']

    if request_type == 'Create':
        try:
            name = event['ResourceProperties']['Name']
            response = client.create_domain(name=name)
            print(f'create_domain response: {response}')
            domain_id = response['domainId']
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS, {'DomainId': domain_id},
                physicalResourceId=domain_id,
            )
        except Exception as e:
            print(f'Error creating domain: {e}')
            cfnresponse.send(event, context, cfnresponse.FAILED, {'Error': str(e)})
        return

    if request_type == 'Delete':
        # Best-effort: never block stack deletion on this preview service.
        try:
            domain_id = event['PhysicalResourceId']
            client.delete_domain(domainId=domain_id)
        except Exception as e:
            print(f'Ignoring error deleting domain (best-effort): {e}')
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
        return

    # Update: domain name changes aren't supported by this resource; no-op.
    cfnresponse.send(
        event, context, cfnresponse.SUCCESS, {},
        physicalResourceId=event['PhysicalResourceId'],
    )
"""
                ),
            )

            domain_resource = CustomResource(
                self,
                "Domain",
                service_token=domain_function.function_arn,
                properties={"Name": connect_health_domain_name},
            )
            self.domain_id = domain_resource.get_att_string("DomainId")

        # --- Connect Health Subscription --------------------------------------
        if existing_subscription_id:
            self.subscription_id = existing_subscription_id
        else:
            subscription_role = iam.Role(
                self,
                "SubscriptionResourceRole",
                assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "service-role/AWSLambdaBasicExecutionRole"
                    )
                ],
            )
            # Service prefix for IAM/ARN purposes is 'health-agent', not 'connecthealth'
            # (see class docstring). Resource ARN format for subscriptions is not yet
            # confirmed by a real error -- kept as a wildcard rather than guessing again.
            subscription_role.add_to_policy(
                iam.PolicyStatement(
                    actions=[
                        "health-agent:CreateSubscription",
                        "health-agent:DeleteSubscription",
                    ],
                    resources=["*"],
                )
            )

            subscription_function = lambda_.Function(
                self,
                "SubscriptionResourceFunction",
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler="index.handler",
                timeout=Duration.seconds(60),
                role=subscription_role,
                code=lambda_.Code.from_inline(
                    """
import boto3
import cfnresponse


def handler(event, context):
    client = boto3.client('connecthealth')
    request_type = event['RequestType']

    if request_type == 'Create':
        try:
            domain_id = event['ResourceProperties']['DomainId']
            response = client.create_subscription(domainId=domain_id)
            print(f'create_subscription response: {response}')
            subscription_id = response['subscriptionId']
            cfnresponse.send(
                event, context, cfnresponse.SUCCESS,
                {'SubscriptionId': subscription_id},
                physicalResourceId=subscription_id,
            )
        except Exception as e:
            print(f'Error creating subscription: {e}')
            cfnresponse.send(event, context, cfnresponse.FAILED, {'Error': str(e)})
        return

    if request_type == 'Delete':
        # Best-effort: never block stack deletion on this preview service.
        try:
            domain_id = event['ResourceProperties']['DomainId']
            subscription_id = event['PhysicalResourceId']
            client.delete_subscription(domainId=domain_id, subscriptionId=subscription_id)
        except Exception as e:
            print(f'Ignoring error deleting subscription (best-effort): {e}')
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
        return

    cfnresponse.send(
        event, context, cfnresponse.SUCCESS, {},
        physicalResourceId=event['PhysicalResourceId'],
    )
"""
                ),
            )

            subscription_resource = CustomResource(
                self,
                "Subscription",
                service_token=subscription_function.function_arn,
                properties={"DomainId": self.domain_id},
            )
            if not existing_domain_id:
                subscription_resource.node.add_dependency(domain_resource)
            self.subscription_id = subscription_resource.get_att_string("SubscriptionId")
