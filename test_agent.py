import unittest
from agent import DebuggingAgent
from troubleshooting import diagnose_error

class AgentTests(unittest.TestCase):
    def test_ec2_ssh(self):
        r = diagnose_error("ssh connection timed out")
        self.assertEqual(r["id"], "ec2-ssh")
        self.assertTrue(any("route table" in s.lower() for s in r["steps"]))
    def test_iam_denied(self):
        self.assertEqual(diagnose_error("User is not authorized to perform s3:GetObject")["id"], "iam-denied")
    def test_s3_403(self):
        self.assertEqual(diagnose_error("S3 403 Forbidden")["id"], "s3-403")
    def test_lambda_timeout(self):
        self.assertEqual(diagnose_error("Task timed out after 30 seconds")["id"], "lambda-timeout")
    def test_cloudformation(self):
        self.assertEqual(diagnose_error("UPDATE_ROLLBACK_COMPLETE")["id"], "cloudformation")
    def test_credentials(self):
        self.assertEqual(diagnose_error("Unable to locate credentials")["id"], "credentials")
    def test_ssm(self):
        self.assertEqual(diagnose_error("TargetNotConnected")["id"], "ssm")
    def test_unknown(self):
        self.assertEqual(diagnose_error("mysterious banana 998")["confidence"], "low")
    def test_contextual_followup(self):
        a = DebuggingAgent()
        a.respond("My EC2 SSH connection times out")
        answer = a.respond("I already checked the security group and port 22 is allowed")
        self.assertIn("won’t repeat", answer)
        self.assertIn("route table", answer.lower())
    def test_empty(self):
        a = DebuggingAgent()
        self.assertIn("describe the aws error", a.respond(" ").lower())

if __name__ == "__main__":
    unittest.main()
