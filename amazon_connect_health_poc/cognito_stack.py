from aws_cdk import (
    CfnParameter,
    CustomResource,
    Duration,
    RemovalPolicy,
    Stack,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_lambda as lambda_,
)
from constructs import Construct


class CognitoStack(Stack):
    """Cognito User Pool for authentication, with a demo user created via custom resource.

    Port of infrastructure/cognito-stack.yaml.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment: str = "dev",
        demo_user_email: str = "connecthealth_demo@example.com",
        demo_user_password: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # NoEcho CFN parameter mirrors the source template's DemoUserPassword parameter:
        # the value is hidden from the console/CLI describe-stacks output, unlike a plain
        # CDK string which would appear in cleartext in the synthesized template.
        #
        # No default is set when demo_user_password isn't supplied (deliberately -- see
        # cdk.json, which never stores a real password): MinLength=8 with an empty-string
        # default fails CDK's own template validation, and more importantly, a required
        # parameter with no default forces `cdk deploy` to demand a real value via
        # `-c demoUserPassword=...` rather than silently deploying a blank password.
        param_kwargs = {
            "type": "String",
            "no_echo": True,
            "min_length": 8,
            "description": "Permanent password for the demo user (min 8 chars, upper + lower + number)",
        }
        if demo_user_password:
            param_kwargs["default"] = demo_user_password
        demo_user_password_param = CfnParameter(self, "DemoUserPassword", **param_kwargs)

        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name=f"connect-health-demo-{environment}",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True, username=False),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(sms=False, otp=True, email=False),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_digits=True,
                require_symbols=False,
                require_uppercase=True,
            ),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
                fullname=cognito.StandardAttribute(required=False, mutable=True),
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.user_pool_client = cognito.UserPoolClient(
            self,
            "UserPoolClient",
            user_pool=self.user_pool,
            user_pool_client_name=f"connect-health-demo-client-{environment}",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=False, admin_user_password=False),
            prevent_user_existence_errors=True,
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30),
            supported_identity_providers=[cognito.UserPoolClientIdentityProvider.COGNITO],
        )

        # Custom resource: create the demo user with a permanent password.
        # No native CDK/CFN resource covers AdminCreateUser + AdminSetUserPassword,
        # so this ports the inline Lambda from the source CFN template verbatim.
        create_user_role = iam.Role(
            self,
            "CreateUserLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        self.user_pool.grant(
            create_user_role, "cognito-idp:AdminCreateUser", "cognito-idp:AdminSetUserPassword"
        )

        create_user_function = lambda_.Function(
            self,
            "CreateUserFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="index.handler",
            timeout=Duration.seconds(30),
            role=create_user_role,
            code=lambda_.Code.from_inline(
                """
import boto3
import cfnresponse


def handler(event, context):
    if event['RequestType'] == 'Delete':
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
        return

    try:
        client = boto3.client('cognito-idp')
        pool_id = event['ResourceProperties']['UserPoolId']
        email = event['ResourceProperties']['Email']
        user_pass = event['ResourceProperties']['Password']

        try:
            client.admin_create_user(
                UserPoolId=pool_id,
                Username=email,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'email_verified', 'Value': 'true'},
                    {'Name': 'name', 'Value': 'Demo User'}
                ],
                TemporaryPassword=user_pass,
                MessageAction='SUPPRESS'
            )
        except client.exceptions.UsernameExistsException:
            pass

        client.admin_set_user_password(
            UserPoolId=pool_id,
            Username=email,
            Password=user_pass,
            Permanent=True
        )

        cfnresponse.send(event, context, cfnresponse.SUCCESS, {'Email': email})
    except Exception as e:
        print(f'Error: {e}')
        cfnresponse.send(event, context, cfnresponse.FAILED, {'Error': str(e)})
"""
            ),
        )

        demo_user = CustomResource(
            self,
            "DemoUser",
            # Invoke the Lambda directly (not via custom_resources.Provider): the
            # handler calls cfnresponse.send() itself, matching the source
            # template's pattern. CloudFormation auto-injects the cfnresponse
            # module only for functions it invokes directly as a ServiceToken
            # with inline ZipFile code — a Provider-wrapped handler would not
            # get it and cfnresponse.send() would fail with ImportError.
            service_token=create_user_function.function_arn,
            properties={
                "UserPoolId": self.user_pool.user_pool_id,
                "Email": demo_user_email,
                "Password": demo_user_password_param.value_as_string,
            },
        )
        demo_user.node.add_dependency(self.user_pool_client)

        self.demo_user_email = demo_user_email
