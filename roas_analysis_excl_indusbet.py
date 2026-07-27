"""
Read-only one-off: ROAS analysis for the last 30 days, EXCLUDING indusbet
(a simple referral channel, not ad-spend-driven, per explicit instruction).
Cohort = users whose FIRST-EVER deposit (is_first_deposit=1) landed within
the last 30 days AND whose acquisition channel is NOT indusbet.
"""
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")
DAILY_DB = os.path.join(BASE, "daily_records.db")

TODAY = datetime(2026, 7, 26).date()
WINDOW_START = (TODAY - timedelta(days=29)).isoformat()
WINDOW_END = TODAY.isoformat()
EXCLUDE_CHANNEL = "indusbet"

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

mconn = sqlite3.connect(MASTER_DB)
vip_by_user = dict(mconn.execute("SELECT user_id, vip_level FROM users").fetchall())
mconn.close()

dconn = sqlite3.connect(DAILY_DB)
all_deposits = dconn.execute(
    "SELECT user_id, order_amount, create_time, status, channel, is_first_deposit FROM deposits "
    "WHERE create_time >= ?",
    (WINDOW_START,),
).fetchall()
all_withdrawals = dconn.execute(
    "SELECT user_id, withdraw_amount, create_time, status FROM withdrawals WHERE create_time >= ?",
    (WINDOW_START,),
).fetchall()
dconn.close()

new_user_channel = {}
new_user_ftd_amount = {}
for user_id, amount, create_time, status, channel, is_first in all_deposits:
    if status != "COMPLETE" or user_id is None or is_first != 1:
        continue
    ch = channel or "Unknown"
    if ch == EXCLUDE_CHANNEL:
        continue
    d = str(create_time)[:10]
    if WINDOW_START <= d <= WINDOW_END:
        new_user_channel[user_id] = ch
        new_user_ftd_amount[user_id] = amount or 0.0

cohort = set(new_user_channel.keys())

cohort_deposit_total = 0.0
cohort_deposit_count = 0
for user_id, amount, create_time, status, channel, is_first in all_deposits:
    if status != "COMPLETE" or user_id not in cohort:
        continue
    cohort_deposit_total += amount or 0.0
    cohort_deposit_count += 1

cohort_withdraw_total = 0.0
cohort_withdraw_count = 0
for user_id, amount, create_time, status in all_withdrawals:
    if status != 2 or user_id not in cohort:
        continue
    cohort_withdraw_total += amount or 0.0
    cohort_withdraw_count += 1

dep_by_user = defaultdict(float)
dep_count_by_user = defaultdict(int)
wd_by_user = defaultdict(float)
for user_id, amount, create_time, status, channel, is_first in all_deposits:
    if status != "COMPLETE" or user_id not in cohort:
        continue
    dep_by_user[user_id] += amount or 0.0
    dep_count_by_user[user_id] += 1
for user_id, amount, create_time, status in all_withdrawals:
    if status != 2 or user_id not in cohort:
        continue
    wd_by_user[user_id] += amount or 0.0

by_channel = defaultdict(lambda: {"users": 0, "ftd_amount": 0.0, "total_deposit": 0.0, "deposit_count": 0, "total_withdraw": 0.0})
for user_id in cohort:
    ch = new_user_channel[user_id]
    row = by_channel[ch]
    row["users"] += 1
    row["ftd_amount"] += new_user_ftd_amount[user_id]
    row["total_deposit"] += dep_by_user.get(user_id, 0.0)
    row["deposit_count"] += dep_count_by_user.get(user_id, 0)
    row["total_withdraw"] += wd_by_user.get(user_id, 0.0)

channel_rows = []
for ch, row in by_channel.items():
    channel_rows.append({
        "channel": ch, "users": row["users"], "ftd_amount": round(row["ftd_amount"], 2),
        "total_deposit": round(row["total_deposit"], 2), "deposit_count": row["deposit_count"],
        "total_withdraw": round(row["total_withdraw"], 2),
        "net_revenue": round(row["total_deposit"] - row["total_withdraw"], 2),
    })
channel_rows.sort(key=lambda r: -r["total_deposit"])

vip_dist = defaultdict(int)
for user_id in cohort:
    vip = vip_by_user.get(user_id)
    vip_dist[vip] += 1

result = {
    "window_start": WINDOW_START,
    "window_end": WINDOW_END,
    "excluded_channel": EXCLUDE_CHANNEL,
    "new_user_count": len(cohort),
    "total_ftd_amount": round(sum(new_user_ftd_amount.values()), 2),
    "cohort_total_deposit": round(cohort_deposit_total, 2),
    "cohort_deposit_count": cohort_deposit_count,
    "cohort_total_withdraw": round(cohort_withdraw_total, 2),
    "cohort_withdraw_count": cohort_withdraw_count,
    "cohort_net_revenue": round(cohort_deposit_total - cohort_withdraw_total, 2),
    "channel_rows": channel_rows,
    "vip_distribution": {str(k): v for k, v in vip_dist.items()},
}

print("=== ROAS_EXCL_JSON_START ===")
print(json.dumps(result, default=str))
print("=== ROAS_EXCL_JSON_END ===")
