"""One-off read-only report: same FD retention metrics as
check_fd_retention_report.py (already deleted), but for a fixed date range
(2026-09-01 through 2026-09-06) in one pass over one DB download. Writes
results to debug/fd_retention_range.json and commits it back to the repo.
One-off; delete both this script and its workflow after use.
"""
import json
import os
import sqlite3
import subprocess
from datetime import date, timedelta

import boto3

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


def compute_for_day(cur, day):
    y_str = day.isoformat()
    next_str = (day + timedelta(days=1)).isoformat()

    fd_user_ids = {
        uid for (uid,) in cur.execute(
            "SELECT DISTINCT user_id FROM deposits "
            "WHERE status = 'COMPLETE' AND is_first_deposit = 1 AND substr(create_time, 1, 10) = ?",
            (y_str,),
        ).fetchall()
        if uid is not None
    }
    fd_count = len(fd_user_ids)
    if not fd_count:
        return {
            "date": y_str, "fd_users": 0, "total_deposit": 0, "bonus_added_users": 0,
            "total_bonus": 0, "bonus_utilised_users": 0, "bonus_utilised_pct": 0,
            "second_deposit_same_day": 0, "second_deposit_conversion_pct": 0,
            "withdraw_same_day_users": 0, "withdraw_same_day_pct": 0,
        }

    placeholders = ",".join("?" * len(fd_user_ids))

    total_deposit = 0.0
    deposit_count_by_user = {}
    for user_id, order_amount in cur.execute(
        f"SELECT user_id, order_amount FROM deposits "
        f"WHERE status = 'COMPLETE' AND user_id IN ({placeholders}) AND substr(create_time, 1, 10) = ?",
        list(fd_user_ids) + [y_str],
    ).fetchall():
        total_deposit += order_amount or 0.0
        deposit_count_by_user[user_id] = deposit_count_by_user.get(user_id, 0) + 1
    second_deposit_same_day = sum(1 for c in deposit_count_by_user.values() if c >= 2)

    bonus_first_credit = {}
    for user_id, create_time in cur.execute(
        f"SELECT user_id, MIN(create_time) FROM bonuses "
        f"WHERE user_id IN ({placeholders}) AND substr(create_time, 1, 10) = ? GROUP BY user_id",
        list(fd_user_ids) + [y_str],
    ).fetchall():
        bonus_first_credit[user_id] = create_time
    bonus_added_users = len(bonus_first_credit)
    total_bonus = 0.0
    for user_id in bonus_first_credit:
        row = cur.execute(
            "SELECT SUM(change_value) FROM bonuses WHERE user_id = ? AND substr(create_time, 1, 10) = ?",
            (user_id, y_str),
        ).fetchone()
        total_bonus += row[0] or 0.0

    utilised_users = 0
    for user_id, credit_time in bonus_first_credit.items():
        row = cur.execute(
            "SELECT 1 FROM wallet_transactions "
            "WHERE user_id = ? AND direction = 1 AND create_time > ? AND substr(create_time, 1, 10) = ? LIMIT 1",
            (user_id, credit_time, y_str),
        ).fetchone()
        if row:
            utilised_users += 1

    withdraw_same_day_users = set()
    for user_id, create_time in cur.execute(
        f"SELECT user_id, create_time FROM withdrawals WHERE user_id IN ({placeholders})",
        list(fd_user_ids),
    ).fetchall():
        if str(create_time)[:10] == y_str:
            withdraw_same_day_users.add(user_id)

    return {
        "date": y_str,
        "fd_users": fd_count,
        "total_deposit": round(total_deposit, 2),
        "bonus_added_users": bonus_added_users,
        "total_bonus": round(total_bonus, 2),
        "bonus_utilised_users": utilised_users,
        "bonus_utilised_pct": round(utilised_users / bonus_added_users * 100, 2) if bonus_added_users else 0,
        "second_deposit_same_day": second_deposit_same_day,
        "second_deposit_conversion_pct": round(second_deposit_same_day / fd_count * 100, 2) if fd_count else 0,
        "withdraw_same_day_users": len(withdraw_same_day_users),
        "withdraw_same_day_pct": round(len(withdraw_same_day_users) / fd_count * 100, 2) if fd_count else 0,
    }


def main():
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    s3.download_file(bucket, "daily_records.db", DAILY_DB)

    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()

    results = []
    day = START
    while day <= END:
        results.append(compute_for_day(cur, day))
        day += timedelta(days=1)

    conn.close()

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "fd_retention_range.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/fd_retention_range.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: FD retention range Sep 1-6"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
