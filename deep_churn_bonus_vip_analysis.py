"""
Read-only one-off: deep root-cause analysis beyond deposits/withdrawals/channels --
(1) actual user churn (who deposited last week but not this week, and why -- VIP
tier, agent, channel, last bonus claimed), (2) VIP-tier breakdown of the deposit
decline, (3) bonus category effectiveness WoW (claims, value, and post-claim
redeposit rate).
"""
import json
import os
import sqlite3
from collections import defaultdict

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")
DAILY_DB = os.path.join(BASE, "daily_records.db")

WEEK1 = [f"2026-07-{d:02d}" for d in range(13, 20)]   # 13-19 Jul (complete)
WEEK2 = [f"2026-07-{d:02d}" for d in range(20, 26)]   # 20-25 Jul (complete, excl. partial 26th)
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
mconn.close()

dconn = sqlite3.connect(DAILY_DB)
deposit_rows = dconn.execute(
    "SELECT user_id, order_amount, create_time, status, pay_channel FROM deposits WHERE create_time >= '2026-07-13'"
).fetchall()
bonus_rows = dconn.execute(
    "SELECT user_id, matched_category, change_value, create_time FROM bonuses WHERE create_time >= '2026-07-13'"
).fetchall()
dconn.close()

# ---- Per-user per-week deposit aggregation ----
dep_by_user_week = defaultdict(lambda: defaultdict(lambda: {"amount": 0.0, "count": 0, "channels": defaultdict(int)}))
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

week1_depositors = {uid for uid, weeks in dep_by_user_week.items() if "week1" in weeks}
week2_depositors = {uid for uid, weeks in dep_by_user_week.items() if "week2" in weeks}
churned = week1_depositors - week2_depositors
retained = week1_depositors & week2_depositors
new_this_week = week2_depositors - week1_depositors

# ---- Bonus claims per user, most recent in week1 (for churn attribution) ----
bonus_by_user_week = defaultdict(lambda: defaultdict(list))
bonus_by_category_week = defaultdict(lambda: defaultdict(lambda: {"claims": 0, "value": 0.0, "users": set()}))
for user_id, category, value, create_time in bonus_rows:
    d = str(create_time)[:10]
    if d in WEEK1_SET:
        wk = "week1"
    elif d in WEEK2_SET:
        wk = "week2"
    else:
        continue
    bonus_by_user_week[user_id][wk].append({"category": category, "value": value or 0.0, "date": create_time})
    cat = category or "Uncategorized"
    bonus_by_category_week[cat][wk]["claims"] += 1
    bonus_by_category_week[cat][wk]["value"] += value or 0.0
    bonus_by_category_week[cat][wk]["users"].add(user_id)

# ---- Churned users detail ----
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
    w1 = dep_by_user_week[uid]["week1"]
    top_channel = max(w1["channels"].items(), key=lambda x: x[1])[0] if w1["channels"] else None
    last_bonus = None
    if uid in bonus_by_user_week and "week1" in bonus_by_user_week[uid]:
        claims = sorted(bonus_by_user_week[uid]["week1"], key=lambda c: c["date"])
        last_bonus = claims[-1]["category"] if claims else None
    churned_detail.append({
        "user_id": uid,
        "vip_level": vip_by_user.get(uid),
        "vip_tier": vip_tier(vip_by_user.get(uid)),
        "agent": agent_by_user.get(uid) or "Un-Assigned",
        "week1_deposit_total": round(w1["amount"], 2),
        "week1_deposit_count": w1["count"],
        "top_channel": top_channel,
        "last_bonus_claimed_week1": last_bonus,
    })
churned_detail.sort(key=lambda r: -r["week1_deposit_total"])

# ---- VIP tier breakdown, both weeks ----
vip_tier_breakdown = defaultdict(lambda: {"week1": {"users": set(), "amount": 0.0}, "week2": {"users": set(), "amount": 0.0}})
for uid, weeks in dep_by_user_week.items():
    tier = vip_tier(vip_by_user.get(uid))
    for wk in ("week1", "week2"):
        if wk in weeks:
            vip_tier_breakdown[tier][wk]["users"].add(uid)
            vip_tier_breakdown[tier][wk]["amount"] += weeks[wk]["amount"]

vip_tier_summary = {}
for tier, data in vip_tier_breakdown.items():
    vip_tier_summary[tier] = {
        "week1_users": len(data["week1"]["users"]),
        "week1_amount": round(data["week1"]["amount"], 2),
        "week2_users": len(data["week2"]["users"]),
        "week2_amount": round(data["week2"]["amount"], 2),
    }

# ---- Bonus category effectiveness + post-claim redeposit rate ----
bonus_category_summary = {}
for cat, weeks in bonus_by_category_week.items():
    w1 = weeks.get("week1", {"claims": 0, "value": 0.0, "users": set()})
    w2 = weeks.get("week2", {"claims": 0, "value": 0.0, "users": set()})
    # redeposit rate: of users who claimed this bonus in week1, how many deposited (any) in week1 AFTER the claim, or in week2 at all
    w1_claimers = w1["users"]
    redeposited = sum(1 for u in w1_claimers if u in week1_depositors or u in week2_depositors)
    bonus_category_summary[cat] = {
        "week1_claims": w1["claims"], "week1_value": round(w1["value"], 2), "week1_unique_users": len(w1["users"]),
        "week2_claims": w2["claims"], "week2_value": round(w2["value"], 2), "week2_unique_users": len(w2["users"]),
        "week1_claimers_redeposit_rate_pct": round(redeposited / len(w1_claimers) * 100, 2) if w1_claimers else None,
    }

result = {
    "week1_depositor_count": len(week1_depositors),
    "week2_depositor_count": len(week2_depositors),
    "churned_count": len(churned),
    "retained_count": len(retained),
    "new_this_week_count": len(new_this_week),
    "churned_total_week1_value": round(sum(c["week1_deposit_total"] for c in churned_detail), 2),
    "churned_detail_top50": churned_detail[:50],
    "vip_tier_summary": vip_tier_summary,
    "bonus_category_summary": bonus_category_summary,
}

print("=== DEEP_ANALYSIS_JSON_START ===")
print(json.dumps(result, default=str))
print("=== DEEP_ANALYSIS_JSON_END ===")
print("SUMMARY: week1_dep=", len(week1_depositors), "week2_dep=", len(week2_depositors),
      "churned=", len(churned), "retained=", len(retained), "new=", len(new_this_week))
