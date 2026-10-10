import unittest
from aws_readonly import execute_readonly_tool

class ReadOnlyToolTests(unittest.TestCase):
    def test_rejects_invalid_instance_id_without_aws_call(self):
        result = execute_readonly_tool("get_ec2_instance_status", {"instance_id": "not-an-id"}, "us-east-1")
        self.assertFalse(result["ok"])
        self.assertIn("exact EC2 instance ID", result["error"])

    def test_rejects_unknown_tool(self):
        result = execute_readonly_tool("run_shell_command", {}, "us-east-1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "Tool is not allowlisted.")

    def test_rejects_invalid_log_group_without_aws_call(self):
        result = execute_readonly_tool("get_cloudwatch_log_events", {"log_group_name": "not-a-log-group"}, "us-east-1")
        self.assertFalse(result["ok"])
        self.assertIn("log group name", result["error"])

if __name__ == "__main__":
    unittest.main()
