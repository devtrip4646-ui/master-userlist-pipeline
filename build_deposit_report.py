"""
Builds an aggregated deposit report -- channel-wise, amount-range, hourly
breakdowns, and success-rate analysis (total vs completed, by amount range /
channel / hour) -- bucketed per calendar date, from the deposits table and
uploads it as JSON to R2 for the "04-project-performance" dashboard Worker.

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


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace(" ", "T"))
    except ValueError:
        return None


def aggregate(records):
    """
    records: list of dicts with keys channel, amount, hour, status,
    completion_minutes, user_id. Returns all report sections for this scope.
    """
    completed = [r for r in records if r["status"] == "COMPLETE"]

    # --- completed-only breakdowns (money/volume of successful deposits) ---
    by_channel = {}
    by_range = {label: {"count": 0, "total_amount": 0.0} for label in RANGE_LABELS}
    by_channel_and_range = {}
    hourly = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"count": 0, "total_amount": 0.0})))
    total_count, total_amount = 0, 0.0

    for r in completed:
        channel, amount, hour = r["channel"], r["amount"], r["hour"]
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

    # --- success-rate breakdowns (all statuses vs completed) ---
    succ_range = {label: {"total": 0, "completed": 0, "min_sum": 0.0, "min_n": 0} for label in RANGE_LABELS}
    succ_channel = {}
    hourly_succ_channel = defaultdict(lambda: defaultdict(lambda: {"total": 0, "completed": 0}))
    hourly_succ_range = defaultdict(lambda: defaultdict(lambda: {"total": 0, "completed": 0}))

    for r in records:
        channel, amount, hour = r["channel"], r["amount"], r["hour"]
        rlabel = bucket_for_amount(amount)
        is_completed = r["status"] == "COMPLETE"

        sr = succ_range[rlabel]
        sr["total"] += 1
        if is_completed:
            sr["completed"] += 1
            if r["completion_minutes"] is not None:
                sr["min_sum"] += r["completion_minutes"]
                sr["min_n"] += 1

        sc = succ_channel.setdefault(channel, {
            "total": 0, "completed": 0, "completed_users": set(), "completed_amount": 0.0, "min_sum": 0.0, "min_n": 0
        })
        sc["total"] += 1
        if is_completed:
            sc["completed"] += 1
            sc["completed_amount"] += amount
            if r["user_id"] is not None:
                sc["completed_users"].add(r["user_id"])
            if r["completion_minutes"] is not None:
                sc["min_sum"] += r["completion_minutes"]
                sc["min_n"] += 1

        if hour is not None:
            hsc = hourly_succ_channel[hour][channel]
            hsc["total"] += 1
            if is_completed:
                hsc["completed"] += 1
            hsr = hourly_succ_range[hour][rlabel]
            hsr["total"] += 1
            if is_completed:
                hsr["completed"] += 1

    def pct(completed, total):
        return round(completed / total * 100, 1) if total else 0

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
        "success_by_range": [
            {
                "range": label,
                "total": v["total"],
                "completed": v["completed"],
                "success_pct": pct(v["completed"], v["total"]),
                "avg_minutes": round(v["min_sum"] / v["min_n"], 1) if v["min_n"] else None,
            }
            for label, v in succ_range.items()
        ],
        "success_by_channel": [
            {
                "channel": ch,
                "total": v["total"],
                "comp_orders": v["completed"],
                "comp_users": len(v["completed_users"]),
                "comp_amount": round(v["completed_amount"], 2),
                "success_pct": pct(v["completed"], v["total"]),
                "avg_minutes": round(v["min_sum"] / v["min_n"], 1) if v["min_n"] else None,
            }
            for ch, v in sorted(succ_channel.items(), key=lambda x: -x[1]["completed_amount"])
        ],
        "hourly_success_by_channel": [
            {"hour": hour, "channel": ch, "total": v["total"], "completed": v["completed"], "success_pct": pct(v["completed"], v["total"])}
            for hour, chans in sorted(hourly_succ_channel.items())
            for ch, v in chans.items()
        ],
        "hourly_success_by_range": [
            {"hour": hour, "range": rl, "total": v["total"], "completed": v["completed"], "success_pct": pct(v["completed"], v["total"])}
            for hour, ranges in sorted(hourly_succ_range.items())
            for rl, v in ranges.items()
        ],
    }


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    rows = cur.execute(
        "SELECT pay_channel, order_amount, create_time, update_time, status, user_id FROM deposits"
    ).fetchall()
    conn.close()

    by_date_records = defaultdict(list)
    all_records = []

    for pay_channel, order_amount, create_time, update_time, status, user_id in rows:
        channel = pay_channel or "Unknown"
        amount = order_amount or 0.0
        date_str, hour = None, None
        create_dt = parse_dt(create_time)
        if create_dt:
            date_str, hour = create_dt.strftime("%Y-%m-%d"), create_dt.hour

        completion_minutes = None
        if status == "COMPLETE":
            update_dt = parse_dt(update_time)
            if create_dt and update_dt:
                completion_minutes = max((update_dt - create_dt).total_seconds() / 60.0, 0)

        record = {
            "channel": channel,
            "amount": amount,
            "hour": hour,
            "status": status,
            "completion_minutes": completion_minutes,
            "user_id": user_id,
        }
        all_records.append(record)
        if date_str:
            by_date_records[date_str].append(record)

    by_date = {date: aggregate(recs) for date, recs in sorted(by_date_records.items())}

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status_filter": "COMPLETE (success-rate sections include all statuses)",
        "amount_ranges": RANGE_LABELS[:-1],
        "dates": sorted(by_date_records.keys()),
        "by_date": by_date,
        "all_time": aggregate(all_records),
    }

    out_path = os.path.join(BASE, "deposit_report.json")
    with open(out_path, "w") as f:
        json.dump(report, f)
    completed_n = sum(1 for r in all_records if r["status"] == "COMPLETE")
    print(f"Wrote {out_path} ({completed_n}/{len(all_records)} completed deposits across {len(by_date)} dates)")

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
