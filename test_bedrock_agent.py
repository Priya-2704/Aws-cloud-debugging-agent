import unittest
from unittest.mock import Mock
from agent import DebuggingAgent
from unittest.mock import patch

class BedrockAgentTests(unittest.TestCase):
    def test_bedrock_converse_response(self):
        agent = DebuggingAgent(use_bedrock=True, model_id="fake-model", region="us-east-1")
        client = Mock()
        client.converse.return_value = {"output": {"message": {"content": [{"text": "Check the Lambda timeout and external API latency."}]}}}
        agent._client = client
        result = agent.respond("Lambda times out calling an API")
        self.assertIn("Check the Lambda timeout", result)
        self.assertEqual(agent.last_mode, "Amazon Bedrock AI")
        client.converse.assert_called_once()

    def test_bedrock_error_falls_back(self):
        agent = DebuggingAgent(use_bedrock=True, model_id="fake-model", region="us-east-1")
        client = Mock()
        client.converse.side_effect = RuntimeError("offline")
        agent._client = client
        result = agent.respond("S3 AccessDenied")
        self.assertIn("Likely diagnosis", result)
        self.assertEqual(agent.last_mode, "Rule-based fallback")
        self.assertIn("Bedrock request failed", agent.last_error)


    @patch("agent.execute_readonly_tool", return_value={"ok": True, "instance_state": "running", "system_status": "ok", "instance_status": "ok"})
    def test_bedrock_readonly_tool_cycle(self, tool_call):
        agent = DebuggingAgent(use_bedrock=True, model_id="fake-model", region="us-east-1", allow_aws_readonly=True)
        client = Mock()
        client.converse.side_effect = [
            {"stopReason": "tool_use", "output": {"message": {"role": "assistant", "content": [{"toolUse": {"toolUseId": "tool-1", "name": "get_ec2_instance_status", "input": {"instance_id": "i-0123456789abcdef0"}}}]}}},
            {"stopReason": "end_turn", "output": {"message": {"content": [{"text": "The instance is running and both status checks are OK."}]}}},
        ]
        agent._client = client
        result = agent.respond("Check EC2 instance i-0123456789abcdef0 status")
        self.assertIn("both status checks are OK", result)
        self.assertEqual(client.converse.call_count, 2)
        tool_call.assert_called_once_with("get_ec2_instance_status", {"instance_id": "i-0123456789abcdef0"}, "us-east-1")

    def test_missing_model_id_uses_fallback(self):
        agent = DebuggingAgent(use_bedrock=True, model_id="")
        result = agent.respond("S3 AccessDenied")
        self.assertIn("Likely diagnosis", result)
        self.assertIn("BEDROCK_MODEL_ID", agent.last_error)

if __name__ == "__main__":
    unittest.main()
