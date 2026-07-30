"""One-off read-only check: prior pass found NO "System Gift" text anywhere
in wallet_transactions, but source_id has many "GiftCode-<hex>" values --
this checks whether THOSE are the rows the user means (blank game_name,
blank source, same shape as the existing "Daily Active Bonus" rule) before
writing a classification rule for them.

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

    print("=== change_desc: total rows starting with 'System Gift' (case-insensitive) ===")
    cd_total = cur.execute(
        "SELECT COUNT(*) FROM wallet_transactions WHERE change_desc LIKE 'System Gift%' COLLATE NOCASE"
    ).fetchone()[0]
    print(" ", cd_total)

    print("=== change_desc: distinct values starting with 'System Gift' ===")
    for row in cur.execute(
        "SELECT change_desc, COUNT(*) FROM wallet_transactions "
        "WHERE change_desc LIKE 'System Gift%' COLLATE NOCASE "
        "GROUP BY change_desc ORDER BY COUNT(*) DESC LIMIT 30"
    ).fetchall():
        print(" ", row)

    print("=== change_desc: game_name / source combos for these rows ===")
    for row in cur.execute(
        "SELECT game_name, source, COUNT(*) FROM wallet_transactions "
        "WHERE change_desc LIKE 'System Gift%' COLLATE NOCASE "
        "GROUP BY game_name, source ORDER BY COUNT(*) DESC LIMIT 20"
    ).fetchall():
        print(" ", row)

    print("=== change_desc: sample 15 raw rows starting with 'System Gift' ===")
    for row in cur.execute(
        "SELECT id, user_id, game_name, source, source_id, change_desc, change_value, change_after, "
        "direction, consume_type, create_time "
        "FROM wallet_transactions WHERE change_desc LIKE 'System Gift%' COLLATE NOCASE "
        "ORDER BY create_time DESC LIMIT 15"
    ).fetchall():
        print(" ", row)

    print("=== change_desc: already classified in bonuses table? ===")
    try:
        cd_matched = cur.execute(
            "SELECT COUNT(*) FROM bonuses WHERE id IN "
            "(SELECT id FROM wallet_transactions WHERE change_desc LIKE 'System Gift%' COLLATE NOCASE)"
        ).fetchone()[0]
        print(" ", cd_matched, "of", cd_total, "already classified")
    except sqlite3.OperationalError as e:
        print("  (bonuses table check failed:", e, ")")

    print("=== change_desc: date range (min/max create_time) ===")
    print(" ", cur.execute(
        "SELECT MIN(create_time), MAX(create_time) FROM wallet_transactions "
        "WHERE change_desc LIKE 'System Gift%' COLLATE NOCASE"
    ).fetchone())

    print()
    print("=== Total rows with source_id LIKE 'GiftCode-%' ===")
    total = cur.execute(
        "SELECT COUNT(*) FROM wallet_transactions WHERE source_id LIKE 'GiftCode-%'"
    ).fetchone()[0]
    print(" ", total)

    print("=== game_name / source combos for GiftCode- rows ===")
    for row in cur.execute(
        "SELECT game_name, source, COUNT(*) FROM wallet_transactions "
        "WHERE source_id LIKE 'GiftCode-%' GROUP BY game_name, source ORDER BY COUNT(*) DESC LIMIT 20"
    ).fetchall():
        print(" ", row)

    print("=== direction / consume_type combos for GiftCode- rows ===")
    for row in cur.execute(
        "SELECT direction, consume_type, COUNT(*) FROM wallet_transactions "
        "WHERE source_id LIKE 'GiftCode-%' GROUP BY direction, consume_type ORDER BY COUNT(*) DESC LIMIT 20"
    ).fetchall():
        print(" ", row)

    print("=== change_value stats for GiftCode- rows (min/max/avg/sum) ===")
    print(" ", cur.execute(
        "SELECT MIN(change_value), MAX(change_value), AVG(change_value), SUM(change_value) "
        "FROM wallet_transactions WHERE source_id LIKE 'GiftCode-%'"
    ).fetchone())

    print("=== Sample 15 raw GiftCode- rows ===")
    for row in cur.execute(
        "SELECT id, user_id, game_name, source, source_id, change_value, change_after, "
        "direction, consume_type, create_time "
        "FROM wallet_transactions WHERE source_id LIKE 'GiftCode-%' ORDER BY create_time DESC LIMIT 15"
    ).fetchall():
        print(" ", row)

    print("=== Are any GiftCode- rows already classified in the bonuses table? ===")
    try:
        matched = cur.execute(
            "SELECT COUNT(*) FROM bonuses WHERE id IN "
            "(SELECT id FROM wallet_transactions WHERE source_id LIKE 'GiftCode-%')"
        ).fetchone()[0]
        print(" ", matched, "of", total, "already classified")
        for row in cur.execute(
            "SELECT DISTINCT matched_category FROM bonuses WHERE id IN "
            "(SELECT id FROM wallet_transactions WHERE source_id LIKE 'GiftCode-%')"
        ).fetchall():
            print("   matched_category:", row)
    except sqlite3.OperationalError as e:
        print("  (bonuses table check failed:", e, ")")

    print("=== Date range of GiftCode- rows (min/max create_time) ===")
    print(" ", cur.execute(
        "SELECT MIN(create_time), MAX(create_time) FROM wallet_transactions WHERE source_id LIKE 'GiftCode-%'"
    ).fetchone())

    conn.close()


if __name__ == "__main__":
    main()
