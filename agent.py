"""AWS debugging agent with Amazon Bedrock LLM reasoning and deterministic fallback."""
from __future__ import annotations
import os
from typing import Optional
from troubleshooting import diagnose_error
from aws_readonly import execute_readonly_tool

SYSTEM_PROMPT = """You are CloudSleuth, a careful AWS troubleshooting assistant for developers and cloud learners.
Analyze the user's symptoms and error text. Use prior conversation context to avoid repeating checks.
Be evidence-led: distinguish facts supplied by the user from hypotheses. Never claim you inspected AWS resources or logs unless they were explicitly provided in chat. Do not invent logs, account settings, or test results.
Give: (1) most likely causes ranked, with confidence described qualitatively (low/medium/high, not percentages); (2) why each cause fits; (3) safe next checks in order; (4) exact AWS Console navigation or read-only AWS CLI commands where useful; (5) one focused follow-up question if needed.
Prefer read-only diagnostics. Never recommend disabling security controls, making a bucket public, using root credentials, or pasting secrets. Do not ask for access keys, secret keys, session tokens, passwords, private keys, or sensitive customer data. For any potentially mutating command, label it clearly and ask the user to review before running. If the issue is unclear, ask a clarifying question instead of guessing. Keep responses practical and understandable to a junior cloud engineer."""

class DebuggingAgent:
    def __init__(self, *, use_bedrock: Optional[bool] = None, region: Optional[str] = None, model_id: Optional[str] = None, allow_aws_readonly: bool = False):
        self.history: list[dict[str, str]] = []
        self.last_diagnosis = None
        self.checked: set[str] = set()
        self.pending_question = None
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.model_id = model_id or os.getenv("BEDROCK_MODEL_ID", "")
        self.allow_aws_readonly = allow_aws_readonly
        self.use_bedrock = (use_bedrock if use_bedrock is not None else os.getenv("BEDROCK_ENABLED", "false").lower() == "true")
        self._client = None
        self.last_mode = "rules"
        self.last_error = None

    def _bedrock_client(self):
        if self._client is None:
            import boto3
            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def respond(self, message: str) -> str:
        text = (message or "").strip()
        if not text:
            return "Please describe the AWS error or symptom so I can help investigate."
        self.history.append({"role": "user", "content": text[:12000]})
        if self.use_bedrock and self.model_id:
            try:
                answer = self._respond_with_bedrock()
                self.last_mode = "Amazon Bedrock AI"
                self.last_error = None
                self.history.append({"role": "assistant", "content": answer})
                return answer
            except Exception as exc:
                # Fail safely and remain usable; don't expose internal details or credentials.
                self.last_error = f"Bedrock request failed ({type(exc).__name__}). Check model access, IAM permissions, region, and AWS credentials."
        self.last_mode = "Rule-based fallback"
        answer = self._respond_with_rules(text)
        self.history.append({"role": "assistant", "content": answer})
        if self.use_bedrock and not self.model_id:
            self.last_error = "Set BEDROCK_MODEL_ID to enable Amazon Bedrock AI mode."
        return answer

    def _respond_with_bedrock(self) -> str:
        # Conversation text is kept as plain user/assistant turns. Tool results are
        # included in the current turn and summarized in the final assistant answer.
        messages = []
        for item in self.history[-12:]:
            role = item["role"]
            content = item["content"].strip()
            if content:
                messages.append({"role": role, "content": [{"text": content[:12000]}]})

        tool_specs = []
        if self.allow_aws_readonly:
            tool_specs = [{"toolSpec": {
                "name": "get_ec2_instance_status",
                "description": "Read status checks for one exact EC2 instance ID in the configured region. Use only when the user supplies an instance ID.",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "instance_id": {"type": "string", "description": "Exact EC2 instance ID, such as i-0123456789abcdef0"}}, "required": ["instance_id"]}}}},
                {"toolSpec": {
                "name": "get_cloudwatch_log_events",
                "description": "Read up to 30 recent events from one exact CloudWatch log group over at most 60 minutes. Use only when the user supplies a log group name and understands logs may contain sensitive data.",
                "inputSchema": {"json": {"type": "object", "properties": {
                    "log_group_name": {"type": "string", "description": "Exact CloudWatch log group name beginning with /"},
                    "minutes": {"type": "integer", "minimum": 1, "maximum": 60},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30}}, "required": ["log_group_name"]}}}}]

        tool_config = {"tools": tool_specs} if tool_specs else None
        # A small bounded loop supports real Bedrock tool use without allowing arbitrary code or shell access.
        for _ in range(3):
            kwargs = {
                "modelId": self.model_id,
                "system": [{"text": SYSTEM_PROMPT + (" You may call only the provided read-only AWS tools when the user has supplied the exact resource identifier. Never infer resource identifiers. Before retrieving logs, warn that log contents may be sensitive." if tool_specs else " Do not claim to have inspected live AWS resources; no AWS diagnostic tools are enabled.") }],
                "messages": messages,
                "inferenceConfig": {"maxTokens": 900, "temperature": 0.2, "topP": 0.9},
            }
            if tool_config:
                kwargs["toolConfig"] = tool_config
            response = self._bedrock_client().converse(**kwargs)
            output_message = response.get("output", {}).get("message", {})
            content_blocks = output_message.get("content", [])
            if response.get("stopReason") != "tool_use":
                answer = "\n".join(block.get("text", "") for block in content_blocks if block.get("text"))
                if not answer.strip():
                    raise RuntimeError("The model returned an empty response")
                safety = "\n\n---\n**Safety:** Recommendations are not proof. Verify results and review suggested changes before acting."
                if not self.allow_aws_readonly:
                    safety += " I have not inspected your AWS account."
                else:
                    safety += " Only the explicitly allowlisted, read-only lookups were available; no resources were modified."
                return answer.strip() + safety

            messages.append(output_message)
            tool_results = []
            for block in content_blocks:
                use = block.get("toolUse")
                if not use:
                    continue
                result = execute_readonly_tool(use.get("name", ""), use.get("input", {}), self.region)
                import json
                tool_results.append({"toolResult": {"toolUseId": use["toolUseId"],
                    "content": [{"json": result}], "status": "success" if result.get("ok") else "error"}})
            if not tool_results:
                raise RuntimeError("Model requested a tool but no valid tool call was returned")
            messages.append({"role": "user", "content": tool_results})
        raise RuntimeError("The agent reached the maximum number of tool-use steps")

    def _respond_with_rules(self, text: str) -> str:
        low = text.lower()
        if any(x in low for x in ["already checked", "already tried", "i checked", "i have checked", "done that", "already verified"]):
            self.checked.add(text)
            if self.last_diagnosis:
                return self._follow_up(text)
        context = " ".join(x["content"] for x in self.history[-6:] if x["role"] == "user")
        result = diagnose_error(text, context=context, previous_checks=self.checked)
        self.last_diagnosis = result
        return self._format(result)

    def _follow_up(self, message):
        if "security group" in message.lower() or "port 22" in message.lower():
            return ("Got it — I’ll treat the security-group/port-22 check as already attempted and won’t repeat it. "
                    "Next, check whether the instance has a reachable public IP (if using public SSH), whether the subnet route table has a route to an internet gateway, "
                    "and whether network ACLs permit inbound SSH and outbound ephemeral return traffic. Also confirm the instance status checks pass. "
                    "Tell me which of those checks you've completed and what you found.")
        return ("I'll record that check as already attempted. Please share the exact result or the next relevant error line. "
                "I'll use it to narrow the remaining possibilities rather than assume the check proved a cause.")

    def _format(self, r):
        out = [f"### Likely diagnosis\n{r['summary']}", f"**Confidence:** {r['confidence']} (heuristic; not a measured probability)", "\n### Evidence and reasoning\n" + r["why"], "\n### Next steps"]
        out += [f"{i}. {s}" for i,s in enumerate(r["steps"],1)]
        if r.get("question"):
            out.append("\n### One useful question\n" + r["question"])
        out.append("\n### Safety\nThis fallback does not access your AWS account or run commands. Start with read-only checks; review commands before running them. Never share credentials or sensitive customer data.")
        return "\n".join(out)
