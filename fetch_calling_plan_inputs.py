import json, os, boto3

def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )

s3 = r2_client()
bucket = os.environ["R2_BUCKET"]
obj = s3.get_object(Bucket=bucket, Key="reports/deposit_report.json")
data = json.loads(obj["Body"].read())

ac = data.get("action_center", {})
result = {}
for key in ["active_low", "active_high", "inactive_low", "inactive_high", "near_upgrade_low", "near_upgrade_high"]:
    rows = ac.get(key, {}).get("rows", [])
    days = [r["inactive_days"] for r in rows if r.get("inactive_days") is not None]
    result[key] = {
        "total_matching": ac.get(key, {}).get("total_matching", len(rows)),
        "min_inactive_days": min(days) if days else None,
        "max_inactive_days": max(days) if days else None,
    }

result["bonus_claims_wallet_bonuses_count"] = len(data.get("bonus_claims", {}).get("wallet_bonuses", []))
result["profit_users_count"] = len(data.get("profit_users", []))
result["weekly_cashback_shield_rows_count"] = len(data.get("weekly_cashback_shield", {}).get("rows", []))

print("=== CALLING_PLAN_INPUTS_JSON_START ===")
print(json.dumps(result, default=str))
print("=== CALLING_PLAN_INPUTS_JSON_END ===")
