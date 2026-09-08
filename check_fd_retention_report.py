"""One-off read-only report: yesterday's first-time depositors (IST) --
total deposit, total bonuses given to them that same day, how many made a
2nd deposit the same day, and how many of them withdrew the same day vs
the next day. Writes results to debug/fd_retention_report.json and commits
it back to the repo so it can be read without needing GitHub Actions log
access. One-off; delete both this script and its workflow after use.
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
    day_after = yesterday + timedelta(days=1)
    y_str = yesterday.isoformat()
    next_str = day_after.isoformat()

    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()

    fd_rows = cur.execute(
        "SELECT user_id, order_amount, create_time FROM deposits "
        "WHERE status = 'COMPLETE' AND is_first_deposit = 1 AND substr(create_time, 1, 10) = ?",
        (y_str,),
    ).fetchall()
    fd_users = {}
    for user_id, order_amount, create_time in fd_rows:
        if user_id is None:
            continue
        fd_users[user_id] = create_time
    fd_user_ids = set(fd_users.keys())
    fd_count = len(fd_user_ids)

    total_deposit = 0.0
    deposit_count_by_user = {}
    if fd_user_ids:
        placeholders = ",".join("?" * len(fd_user_ids))
        for user_id, order_amount, create_time in cur.execute(
            f"SELECT user_id, order_amount, create_time FROM deposits "
            f"WHERE status = 'COMPLETE' AND user_id IN ({placeholders}) AND substr(create_time, 1, 10) = ?",
            list(fd_user_ids) + [y_str],
        ).fetchall():
            total_deposit += order_amount or 0.0
            deposit_count_by_user[user_id] = deposit_count_by_user.get(user_id, 0) + 1

    second_deposit_same_day = sum(1 for c in deposit_count_by_user.values() if c >= 2)

    total_bonus = 0.0
    bonus_user_count = 0
    if fd_user_ids:
        placeholders = ",".join("?" * len(fd_user_ids))
        bonus_rows = cur.execute(
            f"SELECT user_id, SUM(change_value) FROM bonuses "
            f"WHERE user_id IN ({placeholders}) AND substr(create_time, 1, 10) = ? GROUP BY user_id",
            list(fd_user_ids) + [y_str],
        ).fetchall()
        bonus_user_count = len(bonus_rows)
        total_bonus = sum(v or 0.0 for _u, v in bonus_rows)

    withdraw_same_day_users = set()
    withdraw_next_day_users = set()
    if fd_user_ids:
        placeholders = ",".join("?" * len(fd_user_ids))
        for user_id, create_time in cur.execute(
            f"SELECT user_id, create_time FROM withdrawals WHERE user_id IN ({placeholders})",
            list(fd_user_ids),
        ).fetchall():
            day = str(create_time)[:10]
            if day == y_str:
                withdraw_same_day_users.add(user_id)
            elif day == next_str:
                withdraw_next_day_users.add(user_id)

    conn.close()

    result = {
        "date": y_str,
        "fd_users": fd_count,
        "total_deposit": round(total_deposit, 2),
        "bonus_added_users": bonus_user_count,
        "total_bonus": round(total_bonus, 2),
        "second_deposit_same_day": second_deposit_same_day,
        "second_deposit_conversion_pct": round(second_deposit_same_day / fd_count * 100, 2) if fd_count else 0,
        "withdraw_same_day_users": len(withdraw_same_day_users),
        "withdraw_same_day_pct": round(len(withdraw_same_day_users) / fd_count * 100, 2) if fd_count else 0,
        "withdraw_next_day_users": len(withdraw_next_day_users),
        "withdraw_next_day_pct": round(len(withdraw_next_day_users) / fd_count * 100, 2) if fd_count else 0,
    }

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "fd_retention_report.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/fd_retention_report.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: FD retention report for " + y_str], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
