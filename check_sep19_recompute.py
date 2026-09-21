"""One-off read-only check: recompute fd_users_retention_report() for
2026-09-19 against the CURRENT daily_records.db, to see if the zero-bonus
numbers already shown to the user were just a stale snapshot (captured
before the pipeline's retroactive reclassification caught up) rather than
a genuine ongoing data gap. Writes debug/sep19_recompute.json and commits
it back to the repo. One-off; delete this script and its workflow after
use.
"""
import datetime as dt
import json
import os
import subprocess
import sys

import boto3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_deposit_report import fd_users_retention_report

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")


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

    now_dt = dt.datetime(2026, 9, 20, 12, 0, 0)
    result = fd_users_retention_report(DAILY_DB, [], [], now_dt)

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "sep19_recompute.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/sep19_recompute.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: recompute Sep 19 against current db", "--allow-empty"], check=True)

    for attempt in range(5):
        push = subprocess.run(["git", "push"], capture_output=True, text=True)
        if push.returncode == 0:
            break
        print(f"push attempt {attempt + 1} failed, rebasing and retrying:\n{push.stderr}")
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
    else:
        raise RuntimeError("git push failed after 5 rebase-and-retry attempts")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
