"""Read-only one-off: daily attempt/complete counts for the top deposit
channels, to pinpoint exactly which day sathiPay volume collapsed."""
import json
import os
import sqlite3
from collections import defaultdict

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)
bucket = os.environ["R2_BUCKET"]
s3.download_file(bucket, "daily_records.db", DAILY_DB)

conn = sqlite3.connect(DAILY_DB)
rows = conn.execute(
    "SELECT pay_channel, order_amount, status, create_time FROM deposits WHERE create_time >= '2026-07-13'"
).fetchall()
conn.close()

WATCH_CHANNELS = ["Pay Center-sathiPay", "Pay Center-coinsPay", "Pay Center-waasPay", "Pay Center-betixPay-india"]

by_day_channel = defaultdict(lambda: defaultdict(lambda: {"attempts": 0, "complete": 0}))
for pay_channel, amount, status, create_time in rows:
    ch = pay_channel or "Unknown"
    if ch not in WATCH_CHANNELS:
        continue
    d = str(create_time)[:10]
    by_day_channel[ch][d]["attempts"] += 1
    if status == "COMPLETE":
        by_day_channel[ch][d]["complete"] += 1

result = {ch: dict(sorted(days.items())) for ch, days in by_day_channel.items()}
print("=== DAILY_TREND_JSON_START ===")
print(json.dumps(result, default=str))
print("=== DAILY_TREND_JSON_END ===")
