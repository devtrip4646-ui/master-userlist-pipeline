"""
Read-only one-off: FULL list of churned users -- deposited at least once
13-19 Jul (last-last week) but zero deposits 20-26 Jul (last week) -- for a
recovery/reactivation calling list. Uncapped (unlike the top-50 sample used
in the earlier performance-drop report).
"""
import json
import os
import sqlite3
from collections import defaultdict

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")
DAILY_DB = os.path.join(BASE, "daily_records.db")

WEEK1 = [f"2026-07-{d:02d}" for d in range(13, 20)]   # 13-19 Jul
WEEK2 = [f"2026-07-{d:02d}" for d in range(20, 27)]   # 20-26 Jul
WEEK1_SET, WEEK2_SET = set(WEEK1), set(WEEK2)

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
agent_by_user = {}
try:
    agent_by_user = dict(mconn.execute("SELECT user_id, agent_name FROM agent_assignments").fetchall())
except sqlite3.OperationalError:
    pass
banned_ids = set()
try:
    banned_ids = {r[0] for r in mconn.execute("SELECT user_id FROM banned_users").fetchall()}
except sqlite3.OperationalError:
    pass
mconn.close()

dconn = sqlite3.connect(DAILY_DB)
deposit_rows = dconn.execute(
    "SELECT user_id, order_amount, create_time, status, pay_channel FROM deposits WHERE create_time >= '2026-07-13'"
).fetchall()
withdrawal_rows = dconn.execute(
    "SELECT user_id, withdraw_amount, create_time, status FROM withdrawals WHERE create_time >= '2026-07-13'"
).fetchall()
bonus_rows = dconn.execute(
    "SELECT user_id, matched_category, change_value, create_time FROM bonuses WHERE create_time >= '2026-07-13'"
).fetchall()
dconn.close()

dep_by_user_week = defaultdict(lambda: defaultdict(lambda: {"amount": 0.0, "count": 0, "channels": defaultdict(int), "last_date": None}))
for user_id, amount, create_time, status, channel in deposit_rows:
    if status != "COMPLETE" or user_id is None:
        continue
    d = str(create_time)[:10]
    if d in WEEK1_SET:
        wk = "week1"
    elif d in WEEK2_SET:
        wk = "week2"
    else:
        continue
    entry = dep_by_user_week[user_id][wk]
    entry["amount"] += amount or 0.0
    entry["count"] += 1
    entry["channels"][channel or "Unknown"] += 1
    if not entry["last_date"] or d > entry["last_date"]:
        entry["last_date"] = d

wd_by_user_week1 = defaultdict(float)
for user_id, amount, create_time, status in withdrawal_rows:
    if status != 2 or user_id is None:
        continue
    d = str(create_time)[:10]
    if d in WEEK1_SET:
        wd_by_user_week1[user_id] += amount or 0.0

bonus_by_user_week1 = defaultdict(list)
for user_id, category, value, create_time in bonus_rows:
    d = str(create_time)[:10]
    if d in WEEK1_SET:
        bonus_by_user_week1[user_id].append({"category": category, "date": create_time})

week1_depositors = {uid for uid, weeks in dep_by_user_week.items() if "week1" in weeks}
week2_depositors = {uid for uid, weeks in dep_by_user_week.items() if "week2" in weeks}
churned = week1_depositors - week2_depositors

def vip_tier(vip):
    if vip is None:
        return "Unknown"
    if vip <= 1:
        return "VIP0-1"
    if vip <= 4:
        return "VIP2-4"
    if vip <= 9:
        return "VIP5-9"
    return "VIP10-15"

churned_detail = []
for uid in churned:
    if uid in banned_ids:
        continue
    w1 = dep_by_user_week[uid]["week1"]
    top_channel = max(w1["channels"].items(), key=lambda x: x[1])[0] if w1["channels"] else None
    last_bonus = None
    claims = bonus_by_user_week1.get(uid, [])
    if claims:
        claims_sorted = sorted(claims, key=lambda c: c["date"])
        last_bonus = claims_sorted[-1]["category"]
    churned_detail.append({
        "user_id": uid,
        "vip_level": vip_by_user.get(uid),
        "vip_tier": vip_tier(vip_by_user.get(uid)),
        "agent": agent_by_user.get(uid) or "Un-Assigned",
        "week1_deposit_total": round(w1["amount"], 2),
        "week1_deposit_count": w1["count"],
        "week1_last_deposit_date": w1["last_date"],
        "week1_withdraw_total": round(wd_by_user_week1.get(uid, 0.0), 2),
        "top_channel": top_channel,
        "last_bonus_claimed_week1": last_bonus,
    })
churned_detail.sort(key=lambda r: -r["week1_deposit_total"])

print("=== CHURNED_FULL_LIST_JSON_START ===")
print(json.dumps(churned_detail, default=str))
print("=== CHURNED_FULL_LIST_JSON_END ===")
print("TOTAL_CHURNED:", len(churned_detail))
