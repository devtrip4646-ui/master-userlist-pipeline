"""
Read-only one-off: deposit ATTEMPT-level health by payment channel, comparing
last week (13-19 Jul) vs this week-to-date (20-26 Jul), to find whether a
completion-rate/channel problem (not just fewer users) explains the WoW drop
in completed deposits.
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
rows = conn.execute(
    "SELECT pay_channel, order_amount, status, create_time FROM deposits WHERE create_time >= '2026-07-13'"
).fetchall()
conn.close()

LAST_WEEK = {f"2026-07-{d:02d}" for d in range(13, 20)}
THIS_WEEK = {f"2026-07-{d:02d}" for d in range(20, 27)}

def week_stats(rows, dates):
    by_channel = defaultdict(lambda: defaultdict(lambda: {"count": 0, "amount": 0.0}))
    totals = defaultdict(lambda: {"count": 0, "amount": 0.0})
    for pay_channel, amount, status, create_time in rows:
        d = str(create_time)[:10]
        if d not in dates:
            continue
        ch = pay_channel or "Unknown"
        by_channel[ch][status]["count"] += 1
        by_channel[ch][status]["amount"] += amount or 0.0
        totals[status]["count"] += 1
        totals[status]["amount"] += amount or 0.0
    return by_channel, totals

lw_by_channel, lw_totals = week_stats(rows, LAST_WEEK)
tw_by_channel, tw_totals = week_stats(rows, THIS_WEEK)

def channel_summary(by_channel):
    out = []
    for ch, statuses in by_channel.items():
        total_attempts = sum(s["count"] for s in statuses.values())
        complete = statuses.get("COMPLETE", {"count": 0, "amount": 0.0})
        process = statuses.get("PROCESS", {"count": 0, "amount": 0.0})
        failed = statuses.get("FAILED", {"count": 0, "amount": 0.0})
        out.append({
            "channel": ch,
            "total_attempts": total_attempts,
            "complete_count": complete["count"],
            "complete_amount": round(complete["amount"], 2),
            "process_count": process["count"],
            "process_amount": round(process["amount"], 2),
            "failed_count": failed["count"],
            "failed_amount": round(failed["amount"], 2),
            "completion_rate_pct": round(complete["count"] / total_attempts * 100, 2) if total_attempts else None,
        })
    return sorted(out, key=lambda r: -r["total_attempts"])

result = {
    "last_week_by_channel": channel_summary(lw_by_channel),
    "this_week_by_channel": channel_summary(tw_by_channel),
    "last_week_totals": {k: v for k, v in lw_totals.items()},
    "this_week_totals": {k: v for k, v in tw_totals.items()},
}

print("=== CHANNEL_HEALTH_JSON_START ===")
print(json.dumps(result, default=str))
print("=== CHANNEL_HEALTH_JSON_END ===")
