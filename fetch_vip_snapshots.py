import os, boto3, json

s3 = boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"], region_name="auto")
bucket = os.environ["R2_BUCKET"]

dates = ["2026-06-30", "2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04", "2026-07-05", "2026-07-06", "2026-07-07"]
out = {}
for d in dates:
    key = f"reports/analytics_history/{d}.json"
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        out[d] = json.loads(obj["Body"].read())
        print(f"{d}: FOUND", flush=True)
    except s3.exceptions.NoSuchKey:
        print(f"{d}: MISSING", flush=True)

print("=== VIP_SNAPSHOTS_JSON_START ===")
print(json.dumps(out))
print("=== VIP_SNAPSHOTS_JSON_END ===")
