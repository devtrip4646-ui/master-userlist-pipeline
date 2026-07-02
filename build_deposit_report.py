"""
Builds an aggregated deposit report (channel-wise, amount-range, and hourly
channel x amount-range breakdowns), bucketed per calendar date, from the
deposits table and uploads it as JSON to R2 for the "04-project-performance"
dashboard Worker to serve.

Usage: python3 build_deposit_report.py
Requires daily_records.db to be present locally (already downloaded by the
caller) and R2 credentials in env vars or .r2_credentials.
"""
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "daily_records.db")

AMOUNT_RANGES = [
    (200, 299),
    (300, 499),
    (500, 999),
    (1000, 1999),
    (2000, 4999),
    (5000, 9999),
    (10000, 19999),
    (20000, 50000),
]
RANGE_LABELS = [f"{lo}-{hi}" for lo, hi in AMOUNT_RANGES] + ["Other"]


def bucket_for_amount(amount):
    for lo, hi in AMOUNT_RANGES:
        if lo <= amount <= hi:
            return f"{lo}-{hi}"
    return "Other"


def load_creds():
    creds_path = os.path.join(BASE, ".r2_credentials")
    if os.path.exists(creds_path):
        return dict(line.strip().split("=", 1) for line in open(creds_path) if "=" in line)
    return {
        "R2_ACCESS_KEY_ID": os.environ["R2_ACCESS_KEY_ID"],
        "R2_SECRET_ACCESS_KEY": os.environ["R2_SECRET_ACCESS_KEY"],
        "R2_ENDPOINT_URL": os.environ["R2_ENDPOINT_URL"],
        "R2_BUCKET": os.environ["R2_BUCKET"],
    }


def aggregate(records):
    """records: list of (channel, amount, hour). Returns the four report sections."""
    by_channel = {}
    by_range = {label: {"count": 0, "total_amount": 0.0} for label in RANGE_LABELS}
    by_channel_and_range = {}
    hourly = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"count": 0, "total_amount": 0.0})))

    total_count = 0
    total_amount = 0.0

    for channel, amount, hour in records:
        rlabel = bucket_for_amount(amount)
        total_count += 1
        total_amount += amount

        ch = by_channel.setdefault(channel, {"count": 0, "total_amount": 0.0})
        ch["count"] += 1
        ch["total_amount"] += amount

        by_range[rlabel]["count"] += 1
        by_range[rlabel]["total_amount"] += amount

        cr = by_channel_and_range.setdefault((channel, rlabel), {"count": 0, "total_amount": 0.0})
        cr["count"] += 1
        cr["total_amount"] += amount

        if hour is not None:
            hcr = hourly[hour][channel][rlabel]
            hcr["count"] += 1
            hcr["total_amount"] += amount

    return {
        "totals": {"count": total_count, "total_amount": round(total_amount, 2)},
        "by_channel": [
            {
                "channel": ch,
                "count": v["count"],
                "total_amount": round(v["total_amount"], 2),
                "avg_amount": round(v["total_amount"] / v["count"], 2) if v["count"] else 0,
            }
            for ch, v in sorted(by_channel.items(), key=lambda x: -x[1]["total_amount"])
        ],
        "by_amount_range": [
            {"range": label, "count": by_range[label]["count"], "total_amount": round(by_range[label]["total_amount"], 2)}
            for label in RANGE_LABELS
        ],
        "by_channel_and_range": [
            {"channel": ch, "range": rl, "count": v["count"], "total_amount": round(v["total_amount"], 2)}
            for (ch, rl), v in sorted(by_channel_and_range.items(), key=lambda x: -x[1]["total_amount"])
        ],
        "hourly": [
            {
                "hour": hour,
                "channel": ch,
                "range": rl,
                "count": v["count"],
                "total_amount": round(v["total_amount"], 2),
            }
            for hour, chans in sorted(hourly.items())
            for ch, ranges in chans.items()
            for rl, v in ranges.items()
        ],
    }


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    rows = cur.execute(
        "SELECT pay_channel, order_amount, create_time FROM deposits WHERE status = 'COMPLETE'"
    ).fetchall()
    conn.close()

    by_date_records = defaultdict(list)
    all_records = []

    for pay_channel, order_amount, create_time in rows:
        channel = pay_channel or "Unknown"
        amount = order_amount or 0.0
        date_str, hour = None, None
        if create_time:
            try:
                dt = datetime.fromisoformat(create_time.replace(" ", "T"))
                date_str, hour = dt.strftime("%Y-%m-%d"), dt.hour
            except ValueError:
                pass
        record = (channel, amount, hour)
        all_records.append(record)
        if date_str:
            by_date_records[date_str].append(record)

    by_date = {date: aggregate(recs) for date, recs in sorted(by_date_records.items())}

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status_filter": "COMPLETE",
        "amount_ranges": RANGE_LABELS[:-1],
        "dates": sorted(by_date_records.keys()),
        "by_date": by_date,
        "all_time": aggregate(all_records),
    }

    out_path = os.path.join(BASE, "deposit_report.json")
    with open(out_path, "w") as f:
        json.dump(report, f)
    print(f"Wrote {out_path} ({len(all_records)} completed deposits across {len(by_date)} dates)")

    creds = load_creds()
    s3 = boto3.client(
        "s3",
        endpoint_url=creds["R2_ENDPOINT_URL"],
        aws_access_key_id=creds["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=creds["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    s3.upload_file(out_path, creds["R2_BUCKET"], "reports/deposit_report.json")
    print(f"Uploaded reports/deposit_report.json -> r2://{creds['R2_BUCKET']}/reports/deposit_report.json")


if __name__ == "__main__":
    main()
