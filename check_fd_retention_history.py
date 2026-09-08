"""One-off read-only report: FD Users Retention metrics (same definition as
fd_users_retention_report() in build_deposit_report.py) for each date from
2026-09-01 through 2026-09-06. Writes results to
debug/fd_retention_history.json and commits it back to the repo. One-off;
delete both this script and its workflow after use.
"""
import datetime as dt
import json
import os
import subprocess
import sys
from datetime import date, timedelta

import boto3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_deposit_report import fd_users_retention_report

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")

START = date(2026, 9, 1)
END = date(2026, 9, 6)


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def main():
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    s3.download_file(bucket, "daily_records.db", DAILY_DB)

    results = []
    d = START
    while d <= END:
        # fd_users_retention_report() computes for (now - 1 day), so pass
        # "now" as the day AFTER the target date to get that target date.
        now_for_day = date(d.year, d.month, d.day) + timedelta(days=1)
        now_dt = dt.datetime(now_for_day.year, now_for_day.month, now_for_day.day, 12, 0, 0)
        result = fd_users_retention_report(DAILY_DB, [], [], now_dt)
        results.append(result)
        print(json.dumps(result))
        d += timedelta(days=1)

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "fd_retention_history.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/fd_retention_history.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: FD retention history Sep 1-6"], check=True)
    subprocess.run(["git", "push"], check=True)


if __name__ == "__main__":
    main()
