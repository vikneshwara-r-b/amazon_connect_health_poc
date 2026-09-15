import aws_cdk as core
import aws_cdk.assertions as assertions

from amazon_connect_health_poc.amazon_connect_health_poc_stack import AmazonConnectHealthPocStack

# example tests. To run these tests, uncomment this file along with the example
# resource in amazon_connect_health_poc/amazon_connect_health_poc_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = AmazonConnectHealthPocStack(app, "amazon-connect-health-poc")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
