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
    "action_center": d.get("action_center"),
    "bonus_claims": d.get("bonus_claims"),
    "profit_users_count": len(d.get("profit_users") or []),
    "weekly_cashback_shield": d.get("weekly_cashback_shield"),
}

print("=== CALLING_PLAN_INPUTS_JSON_START ===")
print(json.dumps(out))
print("=== CALLING_PLAN_INPUTS_JSON_END ===")
