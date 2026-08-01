"""One-off read-only check: how many rows actually exist in the `bonuses`
table for today's date, vs what the Bonus Claim Report is showing (3
claims total) -- to determine whether this is an ingestion problem
(today's data genuinely isn't there yet) or a report-generation filtering
bug (data exists but isn't being picked up).

Usage: python3 check_today_bonus_rows.py
"""
import os
import sqlite3
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

    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()

    now_ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
    today_str = now_ist.date().isoformat()
    yesterday_str = (now_ist.date() - timedelta(days=1)).isoformat()
    print("=== now (IST):", now_ist.isoformat(), "today_str:", today_str, "===")

    print("=== bonuses table: row count by create_time date, last 3 days ===")
    for row in cur.execute(
        "SELECT substr(create_time,1,10) AS d, COUNT(*) FROM bonuses "
        "WHERE create_time >= ? GROUP BY d ORDER BY d",
        (yesterday_str,),
    ).fetchall():
        print(" ", row)

    print("=== bonuses table: total row count (all time retained) ===")
    print(" ", cur.execute("SELECT COUNT(*) FROM bonuses").fetchone()[0])

    print("=== bonuses table: MAX(create_time) (most recent bonus row ingested) ===")
    print(" ", cur.execute("SELECT MAX(create_time) FROM bonuses").fetchone()[0])

    print("=== bonuses table: sample of last 10 rows by create_time ===")
    for row in cur.execute(
        "SELECT id, matched_category, user_id, change_value, create_time FROM bonuses "
        "ORDER BY create_time DESC LIMIT 10"
    ).fetchall():
        print(" ", row)

    print("=== wallet_transactions: MAX(create_time) (most recent wallet row ingested at all) ===")
    print(" ", cur.execute("SELECT MAX(create_time) FROM wallet_transactions").fetchone()[0])

    print("=== wallet_transactions: row count for today, and how many look bonus-shaped ===")
    total_today = cur.execute(
        "SELECT COUNT(*) FROM wallet_transactions WHERE create_time >= ?", (today_str,)
    ).fetchone()[0]
    print("  total wallet_transactions rows today:", total_today)
    blank_game_today = cur.execute(
        "SELECT COUNT(*) FROM wallet_transactions WHERE create_time >= ? "
        "AND (game_name IS NULL OR game_name = '')",
        (today_str,),
    ).fetchone()[0]
    print("  of those, blank game_name (bonus-shaped) today:", blank_game_today)
    already_classified_today = cur.execute(
        "SELECT COUNT(*) FROM wallet_transactions w WHERE w.create_time >= ? "
        "AND (w.game_name IS NULL OR w.game_name = '') "
        "AND EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id)",
        (today_str,),
    ).fetchone()[0]
    print("  of those blank-game_name rows, already classified into bonuses:", already_classified_today)

    print("=== backfill_state (rules_version / last_backfilled_id) ===")
    try:
        for row in cur.execute("SELECT key, value FROM backfill_state").fetchall():
            print(" ", row)
    except sqlite3.OperationalError as e:
        print("  (backfill_state check failed:", e, ")")

    conn.close()


if __name__ == "__main__":
    main()
