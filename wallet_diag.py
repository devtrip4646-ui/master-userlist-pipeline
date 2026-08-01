import json
import os
import sqlite3
from collections import Counter

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
    "SELECT consume_type, direction, change_value, game_name FROM wallet_transactions LIMIT 5000"
).fetchall()
conn.close()

consume_type_counter = Counter(r[0] for r in rows)
direction_counter = Counter(r[1] for r in rows)
combo_counter = Counter((r[0], r[1]) for r in rows)
neg_count = sum(1 for r in rows if (r[2] or 0) < 0)
sample_by_combo = {}
for r in rows:
    key = str((r[0], r[1]))
    if key not in sample_by_combo:
        sample_by_combo[key] = r

out = {
    "consume_type_distinct": consume_type_counter.most_common(20),
    "direction_distinct": direction_counter.most_common(20),
    "combo_distinct": [[str(k), v] for k, v in combo_counter.most_common(20)],
    "negative_change_value_count": neg_count,
    "sample_by_combo": {k: v for k, v in sample_by_combo.items()},
}
print("=== WALLET_DIAG_JSON_START ===")
print(json.dumps(out, default=str))
print("=== WALLET_DIAG_JSON_END ===")
