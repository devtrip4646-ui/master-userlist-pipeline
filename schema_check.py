import json
import os
import sqlite3

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")
DAILY_DB = os.path.join(BASE, "daily_records.db")

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)
bucket = os.environ["R2_BUCKET"]
s3.download_file(bucket, "master_userlist.db", MASTER_DB)
s3.download_file(bucket, "daily_records.db", DAILY_DB)

out = {}
mconn = sqlite3.connect(MASTER_DB)
tables = [r[0] for r in mconn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
out["master_tables"] = {}
for t in tables:
    cols = [r[1] for r in mconn.execute(f"PRAGMA table_info({t})").fetchall()]
    out["master_tables"][t] = cols
mconn.close()

dconn = sqlite3.connect(DAILY_DB)
tables2 = [r[0] for r in dconn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
out["daily_tables"] = {}
for t in tables2:
    cols = [r[1] for r in dconn.execute(f"PRAGMA table_info({t})").fetchall()]
    out["daily_tables"][t] = cols

# Sample a few deposit rows to see channel field values
sample = dconn.execute("SELECT * FROM deposits ORDER BY create_time DESC LIMIT 3").fetchall()
dconn.close()
out["sample_deposit_row"] = sample

print("=== SCHEMA_JSON_START ===")
print(json.dumps(out, default=str))
print("=== SCHEMA_JSON_END ===")
