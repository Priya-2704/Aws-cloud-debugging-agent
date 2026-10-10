# AWS Cloud Debugging Agent (CloudSleuth)

CloudSleuth is an AI-assisted AWS troubleshooting copilot. It uses Amazon Bedrock's Converse API to reason about error messages and follow-up details. When explicitly enabled, the model can request two allowlisted read-only AWS tools: EC2 instance status checks and bounded CloudWatch log retrieval. A deterministic rule-based fallback remains available when AI mode is not configured or a model request fails.

## Features

- Streamlit chat interface with investigation reset and sample scenarios.
- **Amazon Bedrock AI mode** for conversational reasoning over the user's error details and recent chat history.
- System instructions designed to distinguish evidence from hypotheses, state uncertainty, ask focused follow-up questions, and prioritize read-only diagnostics.
- Rule-based fallback patterns for EC2 SSH, IAM authorization, S3 403, Lambda timeout, CloudFormation rollback, AWS credential errors, and Systems Manager.
- Graceful fallback if Bedrock cannot be reached; the UI displays a troubleshooting hint.
- Optional read-only EC2 status and CloudWatch log tools, disabled by default and only available in Bedrock AI mode.
- No automatic infrastructure changes, shell execution, or arbitrary AWS API access.

## Architecture

`Streamlit UI → DebuggingAgent → Amazon Bedrock Converse API → allowlisted read-only tools (optional)`

If AI mode is disabled or Bedrock fails, the agent uses `troubleshooting.py` and its deterministic rules. When the user explicitly enables read-only AWS lookups, the model may request only `describe_instance_status` for a supplied EC2 instance ID or `filter_log_events` for a supplied CloudWatch log group (maximum 60 minutes and 30 events). The agent never changes resources or runs arbitrary commands.

## Run locally

Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The app runs in rule-based mode by default. To enable Bedrock AI, configure AWS credentials through the standard AWS SDK credential chain (for example, a local AWS profile or environment supplied by your deployment), then set:

```bash
# macOS/Linux
export BEDROCK_ENABLED=true
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID='YOUR_ENABLED_BEDROCK_MODEL_OR_INFERENCE_PROFILE_ID'

# Windows PowerShell
$env:BEDROCK_ENABLED='true'
$env:AWS_REGION='us-east-1'
$env:BEDROCK_MODEL_ID='YOUR_ENABLED_BEDROCK_MODEL_OR_INFERENCE_PROFILE_ID'
```

Restart Streamlit after setting environment variables. Replace the placeholder with a model ID or inference profile actually available to your AWS account and region. The AWS identity needs permission to invoke the selected model (typically `bedrock:InvokeModel` and/or `bedrock:InvokeModelWithResponseStream`, as applicable). Model availability, access requirements, and charges depend on your AWS account, region, and model. Check the current AWS Bedrock console and pricing before use.

## Tests

```bash
python -m unittest discover -s tests -v
```

Unit tests do not call AWS. A real Bedrock/AWS integration test requires configured credentials, model access, suitable IAM permissions, and may incur charges.

## Safety and limitations

- The app sends chat text to Amazon Bedrock when AI mode is enabled. Do not submit credentials, tokens, private keys, passwords, or sensitive customer data.
- Live AWS access is opt-in and limited to two allowlisted read-only tools. It does not validate every resource setting or run AWS CLI commands.
- CloudWatch logs may contain secrets or personal data. Only retrieve logs you are authorized to access, and avoid sending sensitive log content to an LLM.
- Recommendations are suggestions, not proof. Start with read-only checks and independently verify advice before making changes.
- Never grant broad permissions or use root credentials just to make the demo work. Use a dedicated least-privilege identity and avoid committing credentials to Git.
- Rule-based confidence labels are heuristic, not calibrated probabilities.

## Next development milestone

Add more read-only diagnostic tools only when they can be tightly scoped and audited. Keep any remediation action human-approved.
