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

rep = d.get("withdrawal_amount_range_by_day")
print("present:", rep is not None)
if rep:
    for key in ("today", "yesterday"):
        r = rep.get(key)
        print(key, "date:", r["date"], "totals:", r["totals"])
