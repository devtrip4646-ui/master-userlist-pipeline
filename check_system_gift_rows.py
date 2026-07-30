"""One-off read-only check: inspect wallet_transactions rows whose game_name
starts with "System Gift", to see why classify_bonus() currently misses them
(does source get populated for these? does source_id carry anything useful?)
before designing a new classification rule.

Usage: python3 check_system_gift_rows.py
"""
import os
import sqlite3

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

    print("=== Total wallet_transactions rows with game_name LIKE 'System Gift%' ===")
    total = cur.execute(
        "SELECT COUNT(*) FROM wallet_transactions WHERE game_name LIKE 'System Gift%'"
    ).fetchone()[0]
    print(" ", total)

    print("=== Distinct game_name values matching 'System Gift%' ===")
    for row in cur.execute(
        "SELECT game_name, COUNT(*) FROM wallet_transactions WHERE game_name LIKE 'System Gift%' "
        "GROUP BY game_name ORDER BY COUNT(*) DESC LIMIT 30"
    ).fetchall():
        print(" ", row)

    print("=== Distinct (source, source_id-is-blank?) combos for these rows ===")
    for row in cur.execute(
        "SELECT source, (source_id IS NULL OR source_id = '') AS source_id_blank, COUNT(*) "
        "FROM wallet_transactions WHERE game_name LIKE 'System Gift%' "
        "GROUP BY source, source_id_blank ORDER BY COUNT(*) DESC LIMIT 30"
    ).fetchall():
        print(" ", row)

    print("=== Sample 15 raw rows ===")
    for row in cur.execute(
        "SELECT id, user_id, game_name, source, source_id, change_value, change_after, "
        "direction, consume_type, create_time "
        "FROM wallet_transactions WHERE game_name LIKE 'System Gift%' "
        "ORDER BY create_time DESC LIMIT 15"
    ).fetchall():
        print(" ", row)

    print("=== How many of these rows are already present in the 'bonuses' table? ===")
    try:
        matched = cur.execute(
            "SELECT COUNT(*) FROM bonuses WHERE id IN "
            "(SELECT id FROM wallet_transactions WHERE game_name LIKE 'System Gift%')"
        ).fetchone()[0]
        print(" ", matched, "of", total, "already classified")
    except sqlite3.OperationalError as e:
        print("  (bonuses table check failed:", e, ")")

    print("=== For comparison: a few CONFIRMED real-game rows' source values (non-bonus) ===")
    for row in cur.execute(
        "SELECT game_name, source, COUNT(*) FROM wallet_transactions "
        "WHERE game_name IS NOT NULL AND game_name != '' AND game_name NOT LIKE 'System Gift%' "
        "AND game_name NOT LIKE '%Bonus%' AND game_name NOT LIKE '%Gift%' "
        "GROUP BY game_name, source ORDER BY COUNT(*) DESC LIMIT 10"
    ).fetchall():
        print(" ", row)

    conn.close()


if __name__ == "__main__":
    main()
