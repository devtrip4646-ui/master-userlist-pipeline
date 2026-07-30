"""
Read-only one-off: for the most recent complete day, compute:
- Gross Revenue proxy (Total Deposits - Total Withdrawals, COMPLETE/status=2 only)
- Total Bonus Cost (sum of bonuses.change_value), broken out by category
- NGR = Gross Revenue - Bonus Cost
- Bonus Ratio % = Bonus Cost / Gross Revenue * 100
"""
import json
import os
import sqlite3
from collections import defaultdict

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

# Find the most recent date with a full day of records already in (use max deposit date, then use the day before it as "yesterday/most-recent-complete-day", plus also compute for that max date itself as "today so far" for context).
max_date_row = conn.execute("SELECT MAX(substr(create_time,1,10)) FROM deposits").fetchone()
max_date = max_date_row[0]

from datetime import datetime, timedelta
today = datetime.strptime(max_date, "%Y-%m-%d").date()
yesterday = today - timedelta(days=1)

def day_stats(date_str):
    dep_rows = conn.execute(
        "SELECT order_amount FROM deposits WHERE status='COMPLETE' AND substr(create_time,1,10)=?",
        (date_str,),
    ).fetchall()
    wd_rows = conn.execute(
        "SELECT withdraw_amount FROM withdrawals WHERE status=2 AND substr(create_time,1,10)=?",
        (date_str,),
    ).fetchall()
    bonus_rows = conn.execute(
        "SELECT matched_category, change_value FROM bonuses WHERE substr(create_time,1,10)=?",
        (date_str,),
    ).fetchall()

    total_deposit = sum(r[0] or 0.0 for r in dep_rows)
    total_withdraw = sum(r[0] or 0.0 for r in wd_rows)
    gross_revenue = total_deposit - total_withdraw

    by_category = defaultdict(lambda: {"claims": 0, "value": 0.0})
    total_bonus = 0.0
    for category, value in bonus_rows:
        cat = category or "Uncategorized"
        by_category[cat]["claims"] += 1
        by_category[cat]["value"] += value or 0.0
        total_bonus += value or 0.0

    ngr = gross_revenue - total_bonus
    bonus_ratio_pct = round(total_bonus / gross_revenue * 100, 2) if gross_revenue else None

    return {
        "date": date_str,
        "total_deposit": round(total_deposit, 2),
        "deposit_count": len(dep_rows),
        "total_withdraw": round(total_withdraw, 2),
        "withdraw_count": len(wd_rows),
        "gross_revenue": round(gross_revenue, 2),
        "total_bonus_cost": round(total_bonus, 2),
        "bonus_claims_count": len(bonus_rows),
        "ngr": round(ngr, 2),
        "bonus_ratio_pct": bonus_ratio_pct,
        "bonus_by_category": {
            cat: {"claims": v["claims"], "value": round(v["value"], 2)}
            for cat, v in sorted(by_category.items(), key=lambda x: -x[1]["value"])
        },
    }

result = {
    "max_data_date": max_date,
    "today_so_far": day_stats(today.isoformat()),
    "yesterday_complete": day_stats(yesterday.isoformat()),
}
conn.close()

print("=== BONUS_NGR_JSON_START ===")
print(json.dumps(result, default=str))
print("=== BONUS_NGR_JSON_END ===")
