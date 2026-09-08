"""One-off read-only report: of yesterday's first-time depositors who got a
bonus, how many actually placed a bet (wallet_transactions direction=1)
after their bonus was credited, same day -- i.e. utilised the bonus rather
than just having it sit in their wallet or withdrawing it untouched.
Writes results to debug/fd_bonus_utilization.json and commits it back to
the repo. One-off; delete both this script and its workflow after use.
"""
import json
import os
import sqlite3
import subprocess
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


def main():
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    s3.download_file(bucket, "daily_records.db", DAILY_DB)

    now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    yesterday = (now_ist - timedelta(days=1)).date()
    y_str = yesterday.isoformat()

    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()

    fd_user_ids = {
        uid for (uid,) in cur.execute(
            "SELECT DISTINCT user_id FROM deposits "
            "WHERE status = 'COMPLETE' AND is_first_deposit = 1 AND substr(create_time, 1, 10) = ?",
            (y_str,),
        ).fetchall()
        if uid is not None
    }

    bonus_first_credit = {}
    if fd_user_ids:
        placeholders = ",".join("?" * len(fd_user_ids))
        for user_id, create_time in cur.execute(
            f"SELECT user_id, MIN(create_time) FROM bonuses "
            f"WHERE user_id IN ({placeholders}) AND substr(create_time, 1, 10) = ? GROUP BY user_id",
            list(fd_user_ids) + [y_str],
        ).fetchall():
            bonus_first_credit[user_id] = create_time

    bonus_added_users = len(bonus_first_credit)
    utilised_users = 0
    if bonus_first_credit:
        for user_id, credit_time in bonus_first_credit.items():
            row = cur.execute(
                "SELECT 1 FROM wallet_transactions "
                "WHERE user_id = ? AND direction = 1 AND create_time > ? AND substr(create_time, 1, 10) = ? LIMIT 1",
                (user_id, credit_time, y_str),
            ).fetchone()
            if row:
                utilised_users += 1

    conn.close()

    result = {
        "date": y_str,
        "bonus_added_users": bonus_added_users,
        "bonus_utilised_users": utilised_users,
        "bonus_utilised_pct": round(utilised_users / bonus_added_users * 100, 2) if bonus_added_users else 0,
    }

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "fd_bonus_utilization.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/fd_bonus_utilization.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: FD bonus utilization for " + y_str], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
