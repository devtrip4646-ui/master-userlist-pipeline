"""One-off read-only diagnostic: check wallet_state.json (to see which day
the single-day wallet/detail advance-only-on-success mechanism last
completed) and count deposits/withdrawals/wallet_transactions rows per day
for Sep 16-20, to confirm exactly which days have real gaps after the
3-day outage. Writes results to debug/data_coverage.json and commits it
back to the repo. One-off; delete both this script and its workflow after
use.
"""
import json
import os
import sqlite3
import subprocess

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")
WALLET_STATE_KEY = "reports/wallet_fetch_state.json"


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

    result = {}

    try:
        obj = s3.get_object(Bucket=bucket, Key=WALLET_STATE_KEY)
        result["wallet_state"] = json.loads(obj["Body"].read())
    except Exception as e:
        result["wallet_state_error"] = f"{type(e).__name__}: {e}"

    s3.download_file(bucket, "daily_records.db", DAILY_DB)
    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()

    days = ["2026-09-16", "2026-09-17", "2026-09-18", "2026-09-19", "2026-09-20"]
    coverage = {}
    for d in days:
        dep = cur.execute(
            "SELECT COUNT(*) FROM deposits WHERE substr(create_time,1,10) = ? AND status='COMPLETE'", (d,)
        ).fetchone()[0]
        wd = cur.execute(
            "SELECT COUNT(*) FROM withdrawals WHERE substr(create_time,1,10) = ?", (d,)
        ).fetchone()[0]
        wt = cur.execute(
            "SELECT COUNT(*) FROM wallet_transactions WHERE substr(create_time,1,10) = ?", (d,)
        ).fetchone()[0]
        coverage[d] = {"deposits": dep, "withdrawals": wd, "wallet_transactions": wt}
    result["coverage_by_day"] = coverage
    conn.close()

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "data_coverage.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/data_coverage.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: data coverage check for Sep 16-20"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
