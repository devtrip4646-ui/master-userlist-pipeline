import json
import os
import sqlite3
from collections import Counter

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)
bucket = os.environ["R2_BUCKET"]
s3.download_file(bucket, "master_userlist.db", MASTER_DB)

conn = sqlite3.connect(MASTER_DB)
rows = conn.execute("SELECT register_channel, channel, city FROM users ORDER BY create_time DESC LIMIT 2000").fetchall()
conn.close()

reg_channel_counter = Counter(r[0] for r in rows)
channel_counter = Counter(r[1] for r in rows)
city_sample = [r[2] for r in rows[:30]]

out = {
    "register_channel_distinct": reg_channel_counter.most_common(30),
    "channel_distinct": channel_counter.most_common(30),
    "city_sample": city_sample,
}
print("=== DIAG_JSON_START ===")
print(json.dumps(out, default=str))
print("=== DIAG_JSON_END ===")
