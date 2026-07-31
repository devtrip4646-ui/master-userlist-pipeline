"""
Read-only one-off: New users (first-ever COMPLETE deposit) in the last 4
calendar days, from the live Project 04 dashboard data. Reports:
- channel / channel-group breakdown
- region x channel-group cross-tab
- region x channel cross-tab
- 2nd/3rd deposit progression
- Day 1 / Day 2 exact-day retention
Also emits a flat per-user list (user_id, region, agent, channel,
channel_group, deposit_total, withdraw_total, made_2nd, made_3rd, day1, day2)
for Excel export in the HTML report.
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
max_date_row = dconn.execute("SELECT MAX(substr(create_time,1,10)) FROM deposits").fetchone()
today = datetime.strptime(max_date_row[0], "%Y-%m-%d").date()
window_start = today - timedelta(days=3)  # 4 calendar days inclusive of today
window_end = today
lookahead_end = window_end + timedelta(days=2)  # need +2 days of data for Day-2 retention on the last day's cohort

# Pull ALL deposits from window_start onward (covers new-user identification,
# their subsequent deposits for 2nd/3rd + Day1/Day2 checks).
all_deposits = dconn.execute(
    "SELECT user_id, order_amount, create_time, status, channel, is_first_deposit FROM deposits "
    "WHERE create_time >= ?",
    (window_start.isoformat(),),
).fetchall()
all_withdrawals = dconn.execute(
    "SELECT user_id, withdraw_amount, create_time, status FROM withdrawals WHERE create_time >= ?",
    (window_start.isoformat(),),
).fetchall()
dconn.close()

mconn = sqlite3.connect(MASTER_DB)
region_by_user = dict(mconn.execute("SELECT user_id, city FROM users").fetchall())
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

REFERRAL_SET = {"indusbet", "appshare", "ins"}

def channel_group(ch):
    # NOTE: production users.register_channel is entirely NULL (not populated
    # by ingestion) so the Referral/Organic/Promotion/Other split used for
    # the June test-data cohort cannot be reproduced the same way here.
    # Falls back to classifying directly off the deposit's own channel value:
    # Referral (indusbet/appshare/ins) vs every other channel code (agent/paid).
    if ch is None:
        return "Other Channels"
    cl = str(ch).strip().lower()
    if cl in REFERRAL_SET:
        return "Referral"
    return "Other Channels"

# Identify new-user cohort + their first-deposit channel/date
new_user_channel = {}
new_user_first_date = {}
for user_id, amount, create_time, status, channel, is_first in all_deposits:
    if status != "COMPLETE" or user_id is None or is_first != 1:
        continue
    d = str(create_time)[:10]
    if window_start.isoformat() <= d <= window_end.isoformat():
        if user_id in banned_ids:
            continue
        new_user_channel[user_id] = channel or "Unknown"
        new_user_first_date[user_id] = d

cohort = set(new_user_channel.keys())
print(f"New user cohort ({window_start} to {window_end}): {len(cohort)}")

# All COMPLETE deposits + dates for cohort members (for 2nd/3rd + Day1/Day2)
dep_count_by_user = defaultdict(int)
dep_dates_by_user = defaultdict(set)
dep_total_by_user = defaultdict(float)
for user_id, amount, create_time, status, channel, is_first in all_deposits:
    if status != "COMPLETE" or user_id not in cohort:
        continue
    dep_count_by_user[user_id] += 1
    dep_dates_by_user[user_id].add(str(create_time)[:10])
    dep_total_by_user[user_id] += amount or 0.0

wd_total_by_user = defaultdict(float)
for user_id, amount, create_time, status in all_withdrawals:
    if status != 2 or user_id not in cohort:
        continue
    wd_total_by_user[user_id] += amount or 0.0

def retained_on_day(uid, n):
    fdd = datetime.strptime(new_user_first_date[uid], "%Y-%m-%d").date()
    target = fdd + timedelta(days=n)
    if target > today:
        return None  # not observable yet
    return target.isoformat() in dep_dates_by_user.get(uid, set())

user_rows = []
for uid in cohort:
    region = region_by_user.get(uid) or "Unknown"
    ch = new_user_channel[uid]
    grp = channel_group(ch)
    cnt = dep_count_by_user.get(uid, 0)
    d1 = retained_on_day(uid, 1)
    d2 = retained_on_day(uid, 2)
    user_rows.append({
        "user_id": uid,
        "region": region,
        "agent": agent_by_user.get(uid) or "Un-Assigned",
        "channel": ch,
        "channel_group": grp,
        "first_deposit_date": new_user_first_date[uid],
        "deposit_total": round(dep_total_by_user.get(uid, 0.0), 2),
        "withdraw_total": round(wd_total_by_user.get(uid, 0.0), 2),
        "deposit_count": cnt,
        "made_2nd": cnt >= 2,
        "made_3rd": cnt >= 3,
        "day1_observable": (datetime.strptime(new_user_first_date[uid], "%Y-%m-%d").date() + timedelta(days=1)) <= today,
        "day1_retained": d1,
        "day2_observable": (datetime.strptime(new_user_first_date[uid], "%Y-%m-%d").date() + timedelta(days=2)) <= today,
        "day2_retained": d2,
    })

def agg_report(group_fn):
    groups = defaultdict(lambda: {
        "users": 0, "made_2nd": 0, "made_3rd": 0,
        "day1_observable": 0, "day1_retained": 0, "day2_observable": 0, "day2_retained": 0,
    })
    for r in user_rows:
        g = group_fn(r)
        b = groups[g]
        b["users"] += 1
        if r["made_2nd"]:
            b["made_2nd"] += 1
        if r["made_3rd"]:
            b["made_3rd"] += 1
        if r["day1_observable"]:
            b["day1_observable"] += 1
            if r["day1_retained"]:
                b["day1_retained"] += 1
        if r["day2_observable"]:
            b["day2_observable"] += 1
            if r["day2_retained"]:
                b["day2_retained"] += 1
    out = []
    for g, b in groups.items():
        out.append({
            "group": g, "users": b["users"],
            "made_2nd": b["made_2nd"], "made_2nd_pct": round(b["made_2nd"]/b["users"]*100, 2) if b["users"] else None,
            "made_3rd": b["made_3rd"], "made_3rd_pct": round(b["made_3rd"]/b["users"]*100, 2) if b["users"] else None,
            "day1_observable": b["day1_observable"], "day1_retained": b["day1_retained"],
            "day1_pct": round(b["day1_retained"]/b["day1_observable"]*100, 2) if b["day1_observable"] else None,
            "day2_observable": b["day2_observable"], "day2_retained": b["day2_retained"],
            "day2_pct": round(b["day2_retained"]/b["day2_observable"]*100, 2) if b["day2_observable"] else None,
        })
    return out

channel_report = sorted(agg_report(lambda r: r["channel"]), key=lambda x: -x["users"])
channel_group_report = sorted(agg_report(lambda r: r["channel_group"]), key=lambda x: -x["users"])

def cross_tab(dim1_fn, dim2_fn):
    groups = defaultdict(lambda: defaultdict(int))
    for r in user_rows:
        groups[dim1_fn(r)][dim2_fn(r)] += 1
    return {k: dict(v) for k, v in groups.items()}

region_by_channel_group = cross_tab(lambda r: r["channel_group"], lambda r: r["region"])
region_by_channel = cross_tab(lambda r: r["channel"], lambda r: r["region"])

result = {
    "window_start": window_start.isoformat(),
    "window_end": window_end.isoformat(),
    "today": today.isoformat(),
    "total_new_users": len(cohort),
    "channel_report": channel_report,
    "channel_group_report": channel_group_report,
    "region_by_channel_group": region_by_channel_group,
    "region_by_channel": region_by_channel,
    "user_rows": user_rows,
}

print("=== NEW_USERS_4DAY_JSON_START ===")
print(json.dumps(result, default=str))
print("=== NEW_USERS_4DAY_JSON_END ===")
