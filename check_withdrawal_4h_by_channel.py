"""One-off read-only diagnostic: reproduces the dashboard's "Completed Orders
<4h vs >4h" chart (completed withdrawals, status=2, processing time =
update_time - review_time, bucketed by create-date) for the last 7 dates
including today, plus a per-channel breakdown over the same window: count,
how many took >4h, % over 4h, average and median processing hours, and a
channel x day >4h% matrix. Always writes debug/withdrawal_4h_by_channel.json
(including a traceback on failure) and commits it. One-off; delete this
script and its workflow after use.
"""
import json
import os
import sqlite3
import statistics
import subprocess
import traceback
from collections import defaultdict
from datetime import datetime, timedelta

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")
WINDOW_DAYS = 7


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace(" ", "T"))
    except ValueError:
        return None


def run(result):
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    s3.download_file(bucket, "daily_records.db", DAILY_DB)

    today = (datetime.utcnow() + timedelta(hours=5, minutes=30)).date()
    dates = [(today - timedelta(days=i)).isoformat() for i in range(WINDOW_DAYS - 1, -1, -1)]
    result["dates"] = dates

    conn = sqlite3.connect(DAILY_DB)
    rows = conn.execute(
        "SELECT create_time, review_time, update_time, payment_channel FROM withdrawals "
        "WHERE status = 2 AND substr(create_time, 1, 10) >= ? AND substr(create_time, 1, 10) <= ?",
        (dates[0], dates[-1]),
    ).fetchall()
    conn.close()
    result["completed_rows_scanned"] = len(rows)

    daily = {d: {"within_4h": 0, "more_than_4h": 0} for d in dates}
    ch_hours = defaultdict(list)
    ch_day = defaultdict(lambda: defaultdict(lambda: [0, 0]))  # channel -> date -> [within, over]
    for create_time, review_time, update_time, channel in rows:
        review_dt, update_dt = parse_dt(review_time), parse_dt(update_time)
        if not review_dt or not update_dt:
            continue
        date = str(create_time)[:10]
        if date not in daily:
            continue
        hours = max((update_dt - review_dt).total_seconds() / 3600.0, 0)
        channel = channel or "Unknown"
        ch_hours[channel].append(hours)
        if hours <= 4:
            daily[date]["within_4h"] += 1
            ch_day[channel][date][0] += 1
        else:
            daily[date]["more_than_4h"] += 1
            ch_day[channel][date][1] += 1

    result["daily"] = [{"date": d, **daily[d]} for d in dates]

    channels = []
    for ch, hrs in ch_hours.items():
        total = len(hrs)
        over = sum(1 for h in hrs if h > 4)
        channels.append({
            "channel": ch,
            "completed": total,
            "over_4h": over,
            "pct_over_4h": round(over / total * 100, 1) if total else 0.0,
            "avg_hours": round(sum(hrs) / total, 2),
            "median_hours": round(statistics.median(hrs), 2),
            "max_hours": round(max(hrs), 2),
            "by_day_pct_over_4h": {
                d: (round(v[1] / (v[0] + v[1]) * 100, 1) if (v[0] + v[1]) else None)
                for d, v in ((d, ch_day[ch][d]) for d in dates)
            },
        })
    channels.sort(key=lambda c: -c["over_4h"])
    result["channels"] = channels
    result["status"] = "success"


def main():
    result = {}
    try:
        run(result)
    except Exception:
        result["status"] = "error"
        result["traceback"] = traceback.format_exc()
        print(result["traceback"])

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "withdrawal_4h_by_channel.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "-f", "debug/withdrawal_4h_by_channel.json"], check=True)
    commit = subprocess.run(["git", "commit", "-m", "debug: withdrawal 4h by channel"])
    if commit.returncode == 0:
        for attempt in range(5):
            push = subprocess.run(["git", "push"])
            if push.returncode == 0:
                break
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        else:
            raise RuntimeError("git push failed after 5 rebase retries")
    print(json.dumps(result, indent=2, default=str))

    if result.get("status") != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
