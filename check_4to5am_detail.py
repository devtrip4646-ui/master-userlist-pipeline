"""Follow-up to check_4to5am_activity.py: confirmed create_time is stored
as IST-labeled strings (MAX(create_time) tracked ~25 min behind actual
current IST time, not UTC). Window 2026-08-08 04:00-05:00 IST showed 626
distinct wallet_transactions users vs ~100-170 in adjacent hours -- a real
spike -- while only 40 of those users had a bonus-classified row. This
digs into what the OTHER ~586 users were doing: real game play, a batch
process, or something else, and whether per-user transaction counts look
like broad-shallow (many users, 1-2 txns each) vs normal deep engagement.
"""
import os
import sqlite3
from collections import Counter

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

    START, END = "2026-08-08 04:00:00", "2026-08-08 05:00:00"

    print("=== per-user transaction count distribution, 4-5AM IST (how many rows per distinct user) ===")
    rows = cur.execute(
        "SELECT user_id, COUNT(*) FROM wallet_transactions WHERE create_time >= ? AND create_time < ? GROUP BY user_id",
        (START, END),
    ).fetchall()
    counts = Counter(c for _, c in rows)
    for txn_count in sorted(counts):
        print(f"  {txn_count} txn(s): {counts[txn_count]} users")
    print(f"  total distinct users: {len(rows)}")

    print("\n=== blank vs populated game_name (bonus-shaped vs real game), 4-5AM IST ===")
    blank = cur.execute(
        "SELECT COUNT(*), COUNT(DISTINCT user_id) FROM wallet_transactions "
        "WHERE create_time >= ? AND create_time < ? AND (game_name IS NULL OR game_name = '')",
        (START, END),
    ).fetchone()
    populated = cur.execute(
        "SELECT COUNT(*), COUNT(DISTINCT user_id) FROM wallet_transactions "
        "WHERE create_time >= ? AND create_time < ? AND game_name IS NOT NULL AND game_name != ''",
        (START, END),
    ).fetchone()
    print(f"  blank game_name: {blank[0]} rows, {blank[1]} distinct users")
    print(f"  populated game_name: {populated[0]} rows, {populated[1]} distinct users")

    print("\n=== top 15 game_name values, 4-5AM IST ===")
    for row in cur.execute(
        "SELECT game_name, COUNT(*), COUNT(DISTINCT user_id) FROM wallet_transactions "
        "WHERE create_time >= ? AND create_time < ? GROUP BY game_name ORDER BY COUNT(*) DESC LIMIT 15",
        (START, END),
    ).fetchall():
        print("  ", row)

    print("\n=== top 10 source (provider) values, 4-5AM IST ===")
    for row in cur.execute(
        "SELECT source, COUNT(*), COUNT(DISTINCT user_id) FROM wallet_transactions "
        "WHERE create_time >= ? AND create_time < ? GROUP BY source ORDER BY COUNT(*) DESC LIMIT 10",
        (START, END),
    ).fetchall():
        print("  ", row)

    print("\n=== direction breakdown (0=win/credit, 1=bet/debit), 4-5AM IST ===")
    for row in cur.execute(
        "SELECT direction, COUNT(*), COUNT(DISTINCT user_id) FROM wallet_transactions "
        "WHERE create_time >= ? AND create_time < ? GROUP BY direction",
        (START, END),
    ).fetchall():
        print("  ", row)

    print("\n=== per-minute row/user counts within 4-5AM IST (is it a sudden burst or gradual) ===")
    for row in cur.execute(
        "SELECT substr(create_time,1,16) AS minute, COUNT(*), COUNT(DISTINCT user_id) FROM wallet_transactions "
        "WHERE create_time >= ? AND create_time < ? GROUP BY minute ORDER BY minute",
        (START, END),
    ).fetchall():
        print("  ", row)

    print("\n=== how many of the 4-5AM users are NEW (first-ever activity) vs returning ===")
    print("  (checking whether these user_ids have wallet_transactions rows before 2026-08-08 04:00:00)")
    new_vs_old = cur.execute(
        "SELECT "
        "  SUM(CASE WHEN EXISTS (SELECT 1 FROM wallet_transactions w2 WHERE w2.user_id = w1.user_id AND w2.create_time < ?) THEN 0 ELSE 1 END) AS new_users, "
        "  COUNT(DISTINCT w1.user_id) AS total_users "
        "FROM wallet_transactions w1 WHERE w1.create_time >= ? AND w1.create_time < ?",
        (START, START, END),
    ).fetchone()
    print("  new vs total:", new_vs_old)

    conn.close()


if __name__ == "__main__":
    main()
