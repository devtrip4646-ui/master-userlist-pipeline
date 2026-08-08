"""Follow-up: identify what the ~546 unclassified blank-game_name credit
rows during 2026-08-08 04:00-05:00 IST actually are -- pull their raw
source_id/consume_type/other columns to find a name/label, since they
didn't match any of classify_bonus()'s 5 known rules.
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

    print("=== blank-game_name rows in the window that are NOT in bonuses (the unclassified ~546-user set) ===")
    rows = cur.execute(
        "SELECT w.id, w.user_id, w.consume_type, w.source, w.source_id, w.table_name, w.status, "
        "w.l1_category_id, w.l2_category_id, w.change_value, w.direction, w.create_time "
        "FROM wallet_transactions w "
        "WHERE w.create_time >= ? AND w.create_time < ? AND (w.game_name IS NULL OR w.game_name = '') "
        "AND NOT EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id) "
        "ORDER BY w.create_time LIMIT 30",
        (START, END),
    ).fetchall()
    for r in rows:
        print(" ", r)

    print("\n=== distinct source_id PATTERNS (prefix before any trailing hex/digits) for the unclassified set ===")
    all_source_ids = cur.execute(
        "SELECT w.source_id FROM wallet_transactions w "
        "WHERE w.create_time >= ? AND w.create_time < ? AND (w.game_name IS NULL OR w.game_name = '') "
        "AND NOT EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id)",
        (START, END),
    ).fetchall()
    exact_counter = Counter(r[0] for r in all_source_ids)
    print(f"  total rows: {len(all_source_ids)}, distinct exact source_id values: {len(exact_counter)}")
    print("  top 20 exact source_id values:")
    for val, cnt in exact_counter.most_common(20):
        print("   ", repr(val), cnt)

    print("\n=== distinct consume_type values for the unclassified set ===")
    for row in cur.execute(
        "SELECT w.consume_type, COUNT(*) FROM wallet_transactions w "
        "WHERE w.create_time >= ? AND w.create_time < ? AND (w.game_name IS NULL OR w.game_name = '') "
        "AND NOT EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id) "
        "GROUP BY w.consume_type ORDER BY COUNT(*) DESC",
        (START, END),
    ).fetchall():
        print("  ", row)

    print("\n=== distinct table_name values for the unclassified set ===")
    for row in cur.execute(
        "SELECT w.table_name, COUNT(*) FROM wallet_transactions w "
        "WHERE w.create_time >= ? AND w.create_time < ? AND (w.game_name IS NULL OR w.game_name = '') "
        "AND NOT EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id) "
        "GROUP BY w.table_name ORDER BY COUNT(*) DESC",
        (START, END),
    ).fetchall():
        print("  ", row)

    print("\n=== distinct l1_category_id / l2_category_id for the unclassified set ===")
    for row in cur.execute(
        "SELECT w.l1_category_id, w.l2_category_id, COUNT(*) FROM wallet_transactions w "
        "WHERE w.create_time >= ? AND w.create_time < ? AND (w.game_name IS NULL OR w.game_name = '') "
        "AND NOT EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id) "
        "GROUP BY w.l1_category_id, w.l2_category_id ORDER BY COUNT(*) DESC",
        (START, END),
    ).fetchall():
        print("  ", row)

    print("\n=== change_value distribution for the unclassified set ===")
    for row in cur.execute(
        "SELECT w.change_value, COUNT(*) FROM wallet_transactions w "
        "WHERE w.create_time >= ? AND w.create_time < ? AND (w.game_name IS NULL OR w.game_name = '') "
        "AND NOT EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id) "
        "GROUP BY w.change_value ORDER BY COUNT(*) DESC LIMIT 15",
        (START, END),
    ).fetchall():
        print("  ", row)

    conn.close()


if __name__ == "__main__":
    main()
