"""One-off read-only report: FD Users Retention metrics for 2026-09-07
through 2026-09-13, INCLUDING lossback_utilised_users/pct (added after the
prior Sep 7-13 pull). Writes debug/fd_retention_sep7_13_v2.json and commits
it back to the repo. One-off; delete this script and its workflow after
use.
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

START = date(2026, 9, 7)
END = date(2026, 9, 13)


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
    with open(os.path.join(out_path, "fd_retention_sep7_13_v2.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/fd_retention_sep7_13_v2.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: FD retention Sep 7-13 v2", "--allow-empty"], check=True)

    for attempt in range(5):
        push = subprocess.run(["git", "push"], capture_output=True, text=True)
        if push.returncode == 0:
            break
        print(f"push attempt {attempt + 1} failed, rebasing and retrying:\n{push.stderr}")
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
    else:
        raise RuntimeError("git push failed after 5 rebase-and-retry attempts")

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
