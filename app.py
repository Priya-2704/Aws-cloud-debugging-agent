import os
import streamlit as st
from agent import DebuggingAgent

st.set_page_config(page_title="AWS Cloud Debugging Agent", page_icon="☁️", layout="wide")
st.title("☁️ AWS Cloud Debugging Agent")
st.caption("CloudSleuth — AI-assisted, evidence-led AWS troubleshooting")

with st.sidebar:
    st.header("Agent configuration")
    bedrock_default = os.getenv("BEDROCK_ENABLED", "false").lower() == "true"
    use_ai = st.toggle("Use Amazon Bedrock AI", value=bedrock_default, help="Requires AWS credentials, Bedrock model access, and BEDROCK_MODEL_ID.")
    region = st.text_input("AWS Region", value=os.getenv("AWS_REGION", "us-east-1"))
    model_id = st.text_input("Bedrock model ID / inference profile", value=os.getenv("BEDROCK_MODEL_ID", ""), help="Use a model ID or inference profile enabled in your AWS account and selected region.")
    allow_aws_readonly = st.toggle("Allow read-only AWS lookups", value=False, help="Enables narrowly scoped EC2 status and CloudWatch log lookups. Requires AWS credentials and suitable IAM permissions.")
    if allow_aws_readonly:
        st.warning("CloudWatch logs may contain sensitive data. Only use this with a trusted AWS account and never retrieve data you are not authorized to access.")
    st.caption("AI mode sends the conversation text to Amazon Bedrock. Do not paste secrets or customer data.")
    st.divider()
    st.write("**Diagnostic scope**")
    st.caption("EC2 · IAM · S3 · Lambda · CloudFormation · credentials · Systems Manager")
    st.caption("Optional read-only tools: EC2 instance status checks and bounded CloudWatch log retrieval. No resource changes or shell execution.")
    if st.button("Start new investigation", use_container_width=True):
        st.session_state.agent = DebuggingAgent(use_bedrock=use_ai, region=region, model_id=model_id, allow_aws_readonly=allow_aws_readonly)
        st.session_state.messages = []
        st.rerun()

# Rebuild the agent when its selected configuration changes.
config = (use_ai, region.strip(), model_id.strip(), allow_aws_readonly)
if st.session_state.get("config") != config or "agent" not in st.session_state:
    st.session_state.config = config
    st.session_state.agent = DebuggingAgent(use_bedrock=use_ai, region=region, model_id=model_id, allow_aws_readonly=allow_aws_readonly)
    st.session_state.messages = []
if "messages" not in st.session_state:
    st.session_state.messages = []

if use_ai and model_id.strip():
    st.success(f"AI mode selected · Amazon Bedrock · {region.strip()}")
elif use_ai:
    st.warning("AI mode is selected, but no model ID is configured. Add a Bedrock model ID or inference profile in the sidebar.")
else:
    st.info("Rule-based demo mode. Enable Amazon Bedrock AI in the sidebar for LLM reasoning.")
if allow_aws_readonly and not use_ai:
    st.warning("Read-only AWS tools are only available when Amazon Bedrock AI is enabled.")

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

prompt = st.chat_input("Describe the AWS error or answer the agent's last question…")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Investigating the symptoms…"):
            answer = st.session_state.agent.respond(prompt)
        st.markdown(answer)
    st.session_state.messages.append({"role": "assistant", "content": answer})
    if st.session_state.agent.last_error:
        st.warning("AI request could not be completed: " + st.session_state.agent.last_error + " The response above used the rule-based fallback.")

if not st.session_state.messages:
    st.markdown("### Try a scenario")
    cols = st.columns(3)
    examples = [
        ("EC2 SSH timeout", "My EC2 SSH connection times out. I already checked the security group and port 22 is allowed from my IP."),
        ("S3 AccessDenied", "My application gets AccessDenied when calling s3:GetObject on a bucket. The object exists."),
        ("Lambda timeout", "My Lambda function times out after 30 seconds when calling an external API. How should I debug it?"),
    ]
    for col, (label, example) in zip(cols, examples):
        with col:
            if st.button(label, use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": example})
                answer = st.session_state.agent.respond(example)
                st.session_state.messages.append({"role": "assistant", "content": answer})
                st.rerun()
