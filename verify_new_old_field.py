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

noa = d.get("new_old_user_analysis")
print("present:", noa is not None)
if noa:
    print("daily rows:", len(noa["daily"]))
    print("retention rows:", len(noa["retention"]))
    print("first daily:", noa["daily"][0])
    print("last daily:", noa["daily"][-1])
    print("last retention:", noa["retention"][-1] if noa["retention"] else None)
