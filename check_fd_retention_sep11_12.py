"""One-off read-only report: FD Users Retention metrics for 2026-09-12
(same definition as fd_users_retention_report() in
build_deposit_report.py) -- Sep 11 is already available from the daily
snapshot cron, only Sep 12 (which just closed) needs computing ahead of
today's cron run. Writes debug/fd_retention_sep11_12.json and commits it
back to the repo. One-off; delete this script and its workflow after use.
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

START = date(2026, 9, 12)
END = date(2026, 9, 12)


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
        now_dt = dt.datetime(d.year, d.month, d.day, 12, 0, 0) + timedelta(days=1)
        results.append(fd_users_retention_report(DAILY_DB, [], [], now_dt))
        d += timedelta(days=1)

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "fd_retention_sep11_12.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/fd_retention_sep11_12.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: FD retention Sep 11-12", "--allow-empty"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
