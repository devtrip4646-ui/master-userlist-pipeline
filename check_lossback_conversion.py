"""One-off read-only diagnostic: of all users who ever claimed "New Users
Lossback" (within whatever history daily_records.db's bonuses table still
retains -- confirmed rolling ~33-day window), how many made ANY deposit
strictly AFTER their claim, at any point since (not just same-day) --
today's (partial, still-accumulating) data excluded from both the claim
set and the deposit set, per the user's explicit instruction. Always
writes debug/lossback_conversion.json (including a traceback on failure)
and commits it. One-off; delete this script and its workflow after use.
"""
import json
import os
import sqlite3
import subprocess
import traceback
from datetime import datetime, timedelta

import boto3

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


def run(result):
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    s3.download_file(bucket, "daily_records.db", DAILY_DB)

    today_ist = (datetime.utcnow() + timedelta(hours=5, minutes=30)).date().isoformat()
    result["today_excluded"] = today_ist

    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()

    claim_rows = cur.execute(
        "SELECT user_id, MIN(create_time) FROM bonuses "
        "WHERE matched_category = 'New Users Lossback' AND user_id IS NOT NULL "
        "AND substr(create_time, 1, 10) < ? GROUP BY user_id",
        (today_ist,),
    ).fetchall()
    claim_time_by_user = {uid: ct for uid, ct in claim_rows}
    result["total_lossback_claimers"] = len(claim_time_by_user)

    deposit_rows = cur.execute(
        "SELECT user_id, create_time FROM deposits "
        "WHERE status = 'COMPLETE' AND user_id IS NOT NULL AND substr(create_time, 1, 10) < ?",
        (today_ist,),
    ).fetchall()
    conn.close()

    from collections import defaultdict
    deposits_by_user = defaultdict(list)
    for uid, ct in deposit_rows:
        deposits_by_user[uid].append(ct)

    converted = 0
    for uid, claim_time in claim_time_by_user.items():
        user_deposits = deposits_by_user.get(uid, [])
        if any(dt > claim_time for dt in user_deposits):
            converted += 1

    result["claimed_then_deposited"] = converted
    result["conversion_pct"] = round(converted / len(claim_time_by_user) * 100, 2) if claim_time_by_user else 0.0
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
    with open(os.path.join(out_path, "lossback_conversion.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/lossback_conversion.json"], check=True)
    commit = subprocess.run(["git", "commit", "-m", "debug: lossback conversion check"])
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
