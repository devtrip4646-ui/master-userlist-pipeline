import json
import os

import boto3

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)
bucket = os.environ["R2_BUCKET"]
obj = s3.get_object(Bucket=bucket, Key="reports/deposit_report.json")
d = json.loads(obj["Body"].read())

out = {
    "report_today": d.get("report_today"),
    "latest_record_time": d.get("latest_record_time"),
    "dates": d.get("dates"),
    "by_date": d.get("by_date"),
    "withdrawal_analysis": d.get("withdrawal_analysis"),
    "channel_performance": d.get("channel_performance"),
    "bonus_claims_by_date": d.get("bonus_claims_by_date"),
    "reactivation": d.get("reactivation"),
    "vip_upgrade": d.get("vip_upgrade"),
    "weekly_cashback_shield": d.get("weekly_cashback_shield"),
    "agent_performance": d.get("agent_performance"),
    "agent_performance_targets": d.get("agent_performance_targets"),
    "region_vip_analytics": d.get("region_vip_analytics"),
    "action_center": d.get("action_center"),
    "yesterday_withdrawal_amount_range": d.get("withdrawal_amount_range_by_day"),
    "total_registered_users": d.get("total_registered_users"),
}

print("=== DIAGNOSTICS_JSON_START ===")
print(json.dumps(out, default=str))
print("=== DIAGNOSTICS_JSON_END ===")
