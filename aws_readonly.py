"""Explicitly scoped, read-only AWS diagnostics used by CloudSleuth."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import re

INSTANCE_RE = re.compile(r"^i-[0-9a-f]{8}(?:[0-9a-f]{9})?$")


def get_ec2_instance_status(instance_id: str, region: str) -> dict:
    """Return status checks for one explicitly supplied EC2 instance ID."""
    if not INSTANCE_RE.fullmatch(instance_id or ""):
        return {"ok": False, "error": "Provide one exact EC2 instance ID (i- followed by 8 or 17 hexadecimal characters)."}
    import boto3
    ec2 = boto3.client("ec2", region_name=region)
    response = ec2.describe_instance_status(InstanceIds=[instance_id], IncludeAllInstances=True)
    statuses = response.get("InstanceStatuses", [])
    if not statuses:
        return {"ok": True, "instance_id": instance_id, "found_status": False,
                "note": "No status record returned. Check the region, instance ID, and IAM permissions."}
    item = statuses[0]
    return {"ok": True, "instance_id": instance_id,
            "instance_state": item.get("InstanceState", {}).get("Name"),
            "system_status": item.get("SystemStatus", {}).get("Status"),
            "instance_status": item.get("InstanceStatus", {}).get("Status"),
            "availability_zone": item.get("AvailabilityZone"),
            "note": "Read-only EC2 status check; no resource settings were changed."}


def get_cloudwatch_log_events(log_group_name: str, region: str, minutes: int = 30, limit: int = 30) -> dict:
    """Read a bounded number of recent CloudWatch log events from one named log group."""
    if not isinstance(log_group_name, str) or not log_group_name.startswith("/") or len(log_group_name) > 512:
        return {"ok": False, "error": "Provide the exact CloudWatch log group name, beginning with '/'."}
    minutes = max(1, min(int(minutes), 60))
    limit = max(1, min(int(limit), 30))
    import boto3
    logs = boto3.client("logs", region_name=region)
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(minutes=minutes)).timestamp() * 1000)
    response = logs.filter_log_events(logGroupName=log_group_name, startTime=start_ms, endTime=end_ms, limit=limit)
    events = [{"timestamp_utc": datetime.fromtimestamp(e["timestamp"] / 1000, tz=timezone.utc).isoformat(),
               "message": e.get("message", "")[:2000]} for e in response.get("events", [])]
    return {"ok": True, "log_group_name": log_group_name, "window_minutes": minutes,
            "event_count": len(events), "events": events,
            "note": "Read-only CloudWatch log retrieval. Review log content for secrets before sharing it."}


def execute_readonly_tool(name: str, args: dict, region: str) -> dict:
    """Allowlist dispatcher: only these two read-only operations are callable."""
    try:
        if name == "get_ec2_instance_status":
            return get_ec2_instance_status(str(args.get("instance_id", "")), region)
        if name == "get_cloudwatch_log_events":
            return get_cloudwatch_log_events(str(args.get("log_group_name", "")), region,
                                             args.get("minutes", 30), args.get("limit", 30))
        return {"ok": False, "error": "Tool is not allowlisted."}
    except Exception as exc:
        # Avoid returning exception details that could include request metadata.
        return {"ok": False, "error": f"AWS read-only lookup failed ({type(exc).__name__}). Check region, credentials, and least-privilege IAM permissions."}
