"""
Read-only one-off:
1) Platform-wide game popularity/revenue (wallet_transactions), for the
   "which games to promote" question.
2) Bonus claims by category (bonuses table), for context.
3) Games/bonuses claimed specifically by the July cohort (cross-referenced
   against production data, within whatever of July is still in the rolling
   33-day retention window).
4) New users (first-ever deposit) in the last 3 calendar days, same
   breakdown as the earlier last-4-days report.
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
min_date_row = dconn.execute("SELECT MIN(substr(create_time,1,10)) FROM wallet_transactions").fetchone()
min_wallet_date = min_date_row[0]

# ---- 1) Platform-wide game popularity (whole retained window) ----
wallet_rows = dconn.execute(
    "SELECT game_name, direction, change_value, user_id, status FROM wallet_transactions"
).fetchall()

game_stats = defaultdict(lambda: {"bets": 0, "wins": 0, "total_in": 0.0, "total_out": 0.0, "unique_users": set()})
for game_name, direction, change_value, user_id, status in wallet_rows:
    if not game_name:
        continue
    g = game_stats[game_name]
    cv = change_value or 0.0
    # Classify by sign of change_value (negative = money leaving wallet into
    # the game = a bet; positive = money returning = a win), regardless of
    # the "direction" field's own convention, which isn't documented here.
    if cv < 0:
        g["bets"] += 1
        g["total_out"] += abs(cv)
    else:
        g["wins"] += 1
        g["total_in"] += cv
    if user_id is not None:
        g["unique_users"].add(user_id)

game_popularity = []
for game_name, g in game_stats.items():
    net = g["total_in"] - g["total_out"]
    game_popularity.append({
        "game_name": game_name,
        "unique_users": len(g["unique_users"]),
        "bet_transactions": g["bets"],
        "win_transactions": g["wins"],
        "total_wagered": round(g["total_out"], 2),
        "total_won": round(g["total_in"], 2),
        "house_net": round(-net, 2),  # positive = house profit
    })
game_popularity.sort(key=lambda r: -r["unique_users"])

# ---- 2) Bonus claims by category (whole retained window) ----
bonus_rows = dconn.execute("SELECT matched_category, user_id, change_value FROM bonuses").fetchall()
bonus_by_category = defaultdict(lambda: {"claims": 0, "value": 0.0, "users": set()})
for category, user_id, value in bonus_rows:
    cat = category or "Uncategorized"
    b = bonus_by_category[cat]
    b["claims"] += 1
    b["value"] += value or 0.0
    if user_id is not None:
        b["users"].add(user_id)
bonus_summary = [
    {"category": cat, "claims": b["claims"], "value": round(b["value"], 2), "unique_users": len(b["users"])}
    for cat, b in bonus_by_category.items()
]
bonus_summary.sort(key=lambda r: -r["value"])

# ---- 3) New users in last 3 calendar days ----
window_start = today - timedelta(days=2)
window_end = today

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
    if ch is None:
        return "Other Channels"
    cl = str(ch).strip().lower()
    if cl in REFERRAL_SET:
        return "Referral"
    return "Other Channels"

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

cohort3 = set(new_user_channel.keys())

dep_count_by_user3 = defaultdict(int)
dep_dates_by_user3 = defaultdict(set)
dep_total_by_user3 = defaultdict(float)
for user_id, amount, create_time, status, channel, is_first in all_deposits:
    if status != "COMPLETE" or user_id not in cohort3:
        continue
    dep_count_by_user3[user_id] += 1
    dep_dates_by_user3[user_id].add(str(create_time)[:10])
    dep_total_by_user3[user_id] += amount or 0.0

wd_total_by_user3 = defaultdict(float)
for user_id, amount, create_time, status in all_withdrawals:
    if status != 2 or user_id not in cohort3:
        continue
    wd_total_by_user3[user_id] += amount or 0.0

def retained_on_day3(uid, n):
    fdd = datetime.strptime(new_user_first_date[uid], "%Y-%m-%d").date()
    target = fdd + timedelta(days=n)
    if target > today:
        return None
    return target.isoformat() in dep_dates_by_user3.get(uid, set())

user_rows3 = []
for uid in cohort3:
    region = region_by_user.get(uid) or "Unknown"
    ch = new_user_channel[uid]
    grp = channel_group(ch)
    cnt = dep_count_by_user3.get(uid, 0)
    d1 = retained_on_day3(uid, 1)
    d2 = retained_on_day3(uid, 2)
    user_rows3.append({
        "user_id": uid, "region": region, "agent": agent_by_user.get(uid) or "Un-Assigned",
        "channel": ch, "channel_group": grp, "first_deposit_date": new_user_first_date[uid],
        "deposit_total": round(dep_total_by_user3.get(uid, 0.0), 2),
        "withdraw_total": round(wd_total_by_user3.get(uid, 0.0), 2),
        "deposit_count": cnt, "made_2nd": cnt >= 2, "made_3rd": cnt >= 3,
        "day1_observable": (datetime.strptime(new_user_first_date[uid], "%Y-%m-%d").date() + timedelta(days=1)) <= today,
        "day1_retained": d1,
        "day2_observable": (datetime.strptime(new_user_first_date[uid], "%Y-%m-%d").date() + timedelta(days=2)) <= today,
        "day2_retained": d2,
    })

def agg_report3(group_fn):
    groups = defaultdict(lambda: {"users": 0, "made_2nd": 0, "made_3rd": 0, "day1_observable": 0, "day1_retained": 0, "day2_observable": 0, "day2_retained": 0})
    for r in user_rows3:
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

channel_report3 = sorted(agg_report3(lambda r: r["channel"]), key=lambda x: -x["users"])
channel_group_report3 = sorted(agg_report3(lambda r: r["channel_group"]), key=lambda x: -x["users"])

def cross_tab3(dim1_fn, dim2_fn):
    groups = defaultdict(lambda: defaultdict(int))
    for r in user_rows3:
        groups[dim1_fn(r)][dim2_fn(r)] += 1
    return {k: dict(v) for k, v in groups.items()}

region_by_channel_group3 = cross_tab3(lambda r: r["channel_group"], lambda r: r["region"])
region_by_channel3 = cross_tab3(lambda r: r["channel"], lambda r: r["region"])

result = {
    "today": today.isoformat(),
    "min_wallet_date": min_wallet_date,
    "game_popularity": game_popularity,
    "bonus_summary": bonus_summary,
    "new_users_3day": {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "total_new_users": len(cohort3),
        "channel_report": channel_report3,
        "channel_group_report": channel_group_report3,
        "region_by_channel_group": region_by_channel_group3,
        "region_by_channel": region_by_channel3,
        "user_rows": user_rows3,
    },
}

print("=== GAMES_BONUSES_3DAY_JSON_START ===")
print(json.dumps(result, default=str))
print("=== GAMES_BONUSES_3DAY_JSON_END ===")
