"""
Read-only one-off: VIP 3+ users who attempted 2+ deposits on 19 July 2026,
none of which succeeded (no COMPLETE row that day).
"""
import json
import os
import sqlite3
from collections import defaultdict

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")
DAILY_DB = os.path.join(BASE, "daily_records.db")
TARGET_DATE = "2026-07-19"

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

dconn = sqlite3.connect(DAILY_DB)
statuses = dconn.execute(
    "SELECT DISTINCT status FROM deposits WHERE create_time >= ? AND create_time < ?",
    (TARGET_DATE, TARGET_DATE + " 23:59:59.999"),
).fetchall()
print("DISTINCT_STATUSES:", [s[0] for s in statuses])

rows = dconn.execute(
    "SELECT user_id, order_amount, create_time, status, pay_channel FROM deposits "
    "WHERE user_id IS NOT NULL AND create_time >= ? AND create_time < ?",
    (TARGET_DATE, TARGET_DATE + " 23:59:59.999"),
).fetchall()
dconn.close()

by_user = defaultdict(list)
for user_id, amount, create_time, status, channel in rows:
    if str(create_time)[:10] != TARGET_DATE:
        continue
    by_user[user_id].append({"amount": amount, "create_time": create_time, "status": status, "channel": channel})

mconn = sqlite3.connect(MASTER_DB)
vip_by_user = dict(mconn.execute("SELECT user_id, vip_level FROM users").fetchall())
agent_by_user = {}
try:
    agent_by_user = dict(mconn.execute("SELECT user_id, agent_name FROM agent_assignments").fetchall())
except sqlite3.OperationalError:
    pass
mconn.close()

result = []
for user_id, attempts in by_user.items():
    if len(attempts) < 2:
        continue
    if any(a["status"] == "COMPLETE" for a in attempts):
        continue
    vip = vip_by_user.get(user_id)
    if vip is None or vip < 3:
        continue
    result.append({
        "user_id": user_id,
        "vip_level": vip,
        "agent": agent_by_user.get(user_id) or "Un-Assigned",
        "attempt_count": len(attempts),
        "attempted_amount_total": round(sum(a["amount"] or 0.0 for a in attempts), 2),
        "statuses": sorted({a["status"] for a in attempts}),
        "channels": sorted({a["channel"] or "Unknown" for a in attempts}),
        "attempts": sorted(attempts, key=lambda a: a["create_time"]),
    })

result.sort(key=lambda r: -r["attempt_count"])

print("=== VIP_FAILED_DEPOSITS_JSON_START ===")
print(json.dumps(result))
print("=== VIP_FAILED_DEPOSITS_JSON_END ===")
print("MATCHED_USERS:", len(result))
