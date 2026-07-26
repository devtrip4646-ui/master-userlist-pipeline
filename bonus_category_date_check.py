import json
import os
import sqlite3
from collections import Counter, defaultdict

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
    "SELECT matched_category, create_time FROM bonuses WHERE create_time >= '2026-07-13'"
).fetchall()
conn.close()

WATCH = ["Weekly Loss Bonus", "VIP Week Reward 28", "Super friday - Bonus", "Crash - Bonus", "Jili - Bonus",
         "Weekly Check-IN Bonus", "SPIN FREE", "Low VIP"]

by_cat_date = defaultdict(Counter)
for category, create_time in rows:
    d = str(create_time)[:10]
    if category in WATCH:
        by_cat_date[category][d] += 1

result = {cat: dict(sorted(dates.items())) for cat, dates in by_cat_date.items()}
print("=== BONUS_DATE_CHECK_JSON_START ===")
print(json.dumps(result))
print("=== BONUS_DATE_CHECK_JSON_END ===")
