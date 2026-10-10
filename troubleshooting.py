"""Explainable troubleshooting rules. No live AWS calls are made."""
import re

RULES = [
("ec2-ssh", [r"ssh",r"connection timed out",r"port 22"], "EC2 SSH may be blocked by network reachability or host configuration.",
 "A timeout generally suggests the SSH service is not reachable or return traffic is blocked.",
 ["Confirm the instance is running and EC2 status checks pass.",
  "If using public SSH, verify the instance has a public IPv4 address and is in the expected subnet.",
  "Check the subnet route table for a route to an internet gateway when public SSH is intended.",
  "Review network ACL inbound SSH and outbound ephemeral-port return traffic.",
  "On the instance, verify sshd is running and the host firewall allows SSH."],
 "Are you connecting over the public internet, a VPN, a bastion host, or Systems Manager?"),
("iam-denied", [r"accessdenied",r"access denied",r"not authorized to perform",r"unauthorizedoperation",r"explicit deny"], "The request may be blocked by IAM permissions or an explicit deny.",
 "AWS authorization depends on principal, action, resource, and all applicable policy layers.",
 ["Identify the exact IAM role or user making the request.",
  "Capture the denied action and resource ARN from the error.",
  "Review identity and resource-based policies for that action and resource.",
  "Check permissions boundaries, session policies, Organizations SCPs, and explicit denies.",
  "Use an approved policy simulation or read-only policy review to validate least-privilege access."],
 "Which action and resource ARN appear in the error?"),
("s3-403", [r"s3.*403",r"forbidden",r"getobject.*accessdenied",r"accessdenied.*bucket"], "The S3 request may be blocked by IAM, bucket/object policy, ownership, or encryption permissions.",
 "An S3 403 can arise from several policy layers and, for encrypted objects, KMS permissions.",
 ["Confirm bucket, object key, region, and caller identity.",
  "Check s3:GetObject permission against the correct object ARN.",
  "Review bucket/access-point policies and explicit denies, including SCPs and permissions boundaries.",
  "If SSE-KMS is used, check the KMS key policy and required decrypt permission.",
  "Review Block Public Access and object ownership only if relevant to the access method."],
 "Does the object use SSE-KMS, and is the caller in the same AWS account as the bucket?"),
("lambda-timeout", [r"task timed out",r"lambda.*timeout",r"read timed out"], "The Lambda invocation may exceed its timeout or wait on a slow dependency.",
 "The duration and last log line help distinguish slow code, network failures, retries, and downstream latency.",
 ["Find the invocation in CloudWatch Logs and inspect the last completed operation.",
  "Compare invocation duration with the configured timeout.",
  "Check external API/database latency, retry behavior, and connection timeouts.",
  "If attached to a VPC, verify routes, DNS, security groups, and required NAT/VPC endpoints.",
  "Reproduce with a safe test event before changing timeout or memory."],
 "Does the last CloudWatch log line show which operation was running when it timed out?"),
("cloudformation", [r"rollback_complete",r"stack.*rollback",r"create_failed",r"update_rollback"], "A CloudFormation resource operation failed and the stack entered rollback.",
 "The earliest CREATE_FAILED or UPDATE_FAILED event often contains the root-cause reason; later rollback events may be consequences.",
 ["Open stack Events and locate the first CREATE_FAILED or UPDATE_FAILED event.",
  "Read the underlying resource status reason.",
  "Check resource-specific prerequisites, quotas, naming conflicts, permissions, and regional support.",
  "Correct the original cause and review a change set before retrying.",
  "Avoid deleting or replacing production resources until data-loss and replacement risks are understood."],
 "What is the first failed resource event and its status reason?"),
("credentials", [r"expiredtoken",r"expired token",r"invalidclienttokenid",r"signaturedoesnotmatch",r"unable to locate credentials",r"no credentials"], "The credential provider may be missing, expired, or misconfigured.",
 "Credential-provider and request-signing errors often occur before resource authorization is evaluated.",
 ["Confirm which profile or credential provider the CLI/application uses without printing secrets.",
  "Refresh temporary credentials through the approved SSO or role-assumption workflow.",
  "Check system time and configured region if a signature mismatch is reported.",
  "Verify profile/environment-variable selection without revealing values.",
  "Never put keys or tokens in source code, logs, screenshots, or GitHub."],
 "Are you using AWS SSO, an assumed role, or a local credentials profile?"),
("ssm", [r"ssm.*not connected",r"instance is not connected",r"targetnotconnected",r"session manager.*not available"], "The EC2 instance may not be registered as a healthy Systems Manager managed node.",
 "Systems Manager requires a functioning agent, appropriate instance permissions, and outbound connectivity to its endpoints.",
 ["Confirm SSM Agent is installed and running.",
  "Verify the instance profile grants required Systems Manager permissions.",
  "Check outbound access through NAT or the required VPC endpoints.",
  "Review managed-node status and agent logs.",
  "For private subnets, verify endpoint configuration and DNS."],
 "Is the instance in a private subnet, and does it have the required SSM endpoints or NAT access?")
]

def diagnose_error(error: str, context: str = "", previous_checks=None) -> dict:
    text = (error + " " + context).lower()
    previous_checks = previous_checks or set()
    for rid, patterns, summary, why, steps, question in RULES:
        if any(re.search(p, text, re.I) for p in patterns):
            remaining = list(steps)
            # Skip suggestions explicitly reported as already checked.
            checked_text = " ".join(previous_checks).lower()
            if "security group" in checked_text or "port 22" in checked_text:
                remaining = [s for s in remaining if "security group" not in s.lower() and "port 22" not in s.lower()]
            return {"id":rid,"summary":summary,"confidence":"medium","why":why,"steps":remaining,"question":question}
    return {"id":"unknown","summary":"I can't confidently match this to a known troubleshooting pattern yet.",
      "confidence":"low","why":"The current prototype has a limited rule set and should not guess at an unsupported error.",
      "steps":["Share the full error text and the AWS service/operation involved.","Add non-secret context: region, resource type, recent change, and expected behavior.","Check the relevant AWS service health page and official troubleshooting documentation."],
      "question":"Which AWS service and exact operation produced this error?"}
