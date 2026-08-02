"""
Read-only one-off:
1) Top 20 users by verified loss amount, where loss% > 25% of total deposit,
   AND inactive 9+ days.
2) Users with total lifetime deposit >= Rs 200,000, AND inactive 9+ days.

verified_loss = total_recharge - total_withdrawal - user_balance (money that
came in and isn't in their wallet or paid back out -- i.e. spent on betting),
same definition used by the Weekly Cashback Shield feature elsewhere in this
codebase. loss_pct = verified_loss / total_recharge * 100.

IMPORTANT CAVEAT: total_recharge/total_withdrawal in master_userlist.db are
LIFETIME cumulative totals, continuously synced -- NOT scoped to "last 3
months". daily_records.db (which has day-level detail) only retains a
rolling 33-day window, so a true 3-month transaction-level cut isn't
possible from this data. This report uses lifetime totals as the best
available proxy and flags that explicitly.
"""
import json
import os
import sqlite3
from datetime import datetime

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
rows = conn.execute(
    "SELECT user_id, vip_level, total_recharge, total_withdrawal, user_balance, last_active_time, recharge_count "
    "FROM users"
).fetchall()
agent_by_user = {}
try:
    agent_by_user = dict(conn.execute("SELECT user_id, agent_name FROM agent_assignments").fetchall())
except sqlite3.OperationalError:
    pass
banned_ids = set()
try:
    banned_ids = {r[0] for r in conn.execute("SELECT user_id FROM banned_users").fetchall()}
except sqlite3.OperationalError:
    pass
now_row = conn.execute("SELECT MAX(query_time) FROM users").fetchone()
conn.close()

now = datetime.utcnow()

def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

all_rows = []
for user_id, vip_level, total_recharge, total_withdrawal, user_balance, last_active_time, recharge_count in rows:
    if user_id in banned_ids:
        continue
    tr = total_recharge or 0.0
    tw = total_withdrawal or 0.0
    bal = user_balance or 0.0
    last_active_dt = parse_dt(last_active_time)
    inactive_days = (now - last_active_dt).days if last_active_dt else None
    verified_loss = tr - tw - bal
    loss_pct = round(verified_loss / tr * 100, 2) if tr else None
    all_rows.append({
        "user_id": user_id,
        "vip_level": vip_level,
        "agent": agent_by_user.get(user_id) or "Un-Assigned",
        "total_deposit": round(tr, 2),
        "total_withdrawal": round(tw, 2),
        "wallet_balance": round(bal, 2),
        "verified_loss": round(verified_loss, 2),
        "loss_pct": loss_pct,
        "inactive_days": inactive_days,
        "recharge_count": recharge_count or 0,
    })

# Report A: loss% > 25%, inactive >= 9 days, top 20 by verified_loss amount
report_a = [r for r in all_rows if r["loss_pct"] is not None and r["loss_pct"] > 25 and r["inactive_days"] is not None and r["inactive_days"] >= 9]
report_a.sort(key=lambda r: -r["verified_loss"])
report_a_top20 = report_a[:20]

# Report B: total_deposit >= 200000, inactive >= 9 days
report_b = [r for r in all_rows if r["total_deposit"] >= 200000 and r["inactive_days"] is not None and r["inactive_days"] >= 9]
report_b.sort(key=lambda r: -r["total_deposit"])

result = {
    "generated_at": now.isoformat(),
    "report_a_matching_before_top20": len(report_a),
    "report_a_top20": report_a_top20,
    "report_b_count": len(report_b),
    "report_b": report_b,
}

print("=== LOSS_DEPOSIT_JSON_START ===")
print(json.dumps(result, default=str))
print("=== LOSS_DEPOSIT_JSON_END ===")
print("REPORT_A_MATCHING:", len(report_a))
print("REPORT_B_MATCHING:", len(report_b))
