"""
Read-only one-off: day-wise ROAS breakdown for the last 30 days, excluding
indusbet (referral channel, not ad-spend-driven). For each day: new users
acquired that day, their FTD amount, and that day's total deposit/withdraw/
net-revenue activity from the WHOLE 30-day cohort (not just that day's new
signups) -- i.e. how much revenue the paid-acquisition cohort generated on
each calendar day, plus a cumulative running total against the ₹30L spend.
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
s3.download_file(bucket, "daily_records.db", DAILY_DB)

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

# Cohort: users whose FIRST-EVER deposit landed in the window AND whose
# acquisition channel is NOT indusbet.
cohort = set()
new_users_by_day = defaultdict(list)  # date -> [(user_id, ftd_amount)]
for user_id, amount, create_time, status, channel, is_first in all_deposits:
    if status != "COMPLETE" or user_id is None or is_first != 1:
        continue
    ch = channel or "Unknown"
    if ch == EXCLUDE_CHANNEL:
        continue
    d = str(create_time)[:10]
    if WINDOW_START <= d <= WINDOW_END:
        cohort.add(user_id)
        new_users_by_day[d].append((user_id, amount or 0.0))

# Day-wise deposit/withdraw activity from the WHOLE cohort (any day, not
# just their signup day).
deposit_by_day = defaultdict(float)
for user_id, amount, create_time, status, channel, is_first in all_deposits:
    if status != "COMPLETE" or user_id not in cohort:
        continue
    d = str(create_time)[:10]
    deposit_by_day[d] += amount or 0.0

withdraw_by_day = defaultdict(float)
for user_id, amount, create_time, status in all_withdrawals:
    if status != 2 or user_id not in cohort:
        continue
    d = str(create_time)[:10]
    withdraw_by_day[d] += amount or 0.0

daily_rows = []
d = datetime.strptime(WINDOW_START, "%Y-%m-%d").date()
end = datetime.strptime(WINDOW_END, "%Y-%m-%d").date()
while d <= end:
    dstr = d.isoformat()
    new_users = new_users_by_day.get(dstr, [])
    daily_rows.append({
        "date": dstr,
        "new_users": len(new_users),
        "ftd_amount": round(sum(a for _, a in new_users), 2),
        "cohort_deposit": round(deposit_by_day.get(dstr, 0.0), 2),
        "cohort_withdraw": round(withdraw_by_day.get(dstr, 0.0), 2),
        "cohort_net_revenue": round(deposit_by_day.get(dstr, 0.0) - withdraw_by_day.get(dstr, 0.0), 2),
    })
    d += timedelta(days=1)

print("=== ROAS_DAYWISE_JSON_START ===")
print(json.dumps(daily_rows))
print("=== ROAS_DAYWISE_JSON_END ===")
