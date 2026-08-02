"""One-off read-only check: user reports "Weekly Loss Bonus" shows up in
the Search User page's Bonuses Claimed list for some users but not others.
classify_bonus()'s rule 1 requires game_name to be a real bonus name AND
source to be BLANK -- if "Weekly Loss Bonus" rows sometimes carry a
non-blank source, those instances would never make it into the `bonuses`
table at all (classify_bonus returns None), explaining inconsistent
per-user visibility. Check the actual distribution.
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

    print("=== distinct game_name values LIKE '%Weekly Loss%' (catches whitespace/case variants) ===")
    for row in cur.execute(
        "SELECT game_name, COUNT(*) FROM wallet_transactions WHERE game_name LIKE '%Weekly Loss%' GROUP BY game_name"
    ).fetchall():
        print(" ", repr(row[0]), row[1])

    print("=== exact game_name = 'Weekly Loss Bonus': total count, and count by (source IS blank) ===")
    print(" total:", cur.execute("SELECT COUNT(*) FROM wallet_transactions WHERE game_name = 'Weekly Loss Bonus'").fetchone()[0])
    for row in cur.execute(
        "SELECT CASE WHEN source IS NULL OR source = '' THEN 'BLANK' ELSE source END AS src, COUNT(*) "
        "FROM wallet_transactions WHERE game_name = 'Weekly Loss Bonus' GROUP BY src ORDER BY COUNT(*) DESC LIMIT 20"
    ).fetchall():
        print(" ", row)

    print("=== sample of 10 'Weekly Loss Bonus' rows (id, user_id, source, source_id, create_time) ===")
    for row in cur.execute(
        "SELECT id, user_id, source, source_id, create_time FROM wallet_transactions "
        "WHERE game_name = 'Weekly Loss Bonus' ORDER BY create_time DESC LIMIT 10"
    ).fetchall():
        print(" ", row)

    print("=== how many of those ids are actually present in bonuses table ===")
    total_wt = cur.execute("SELECT COUNT(*) FROM wallet_transactions WHERE game_name = 'Weekly Loss Bonus'").fetchone()[0]
    matched_in_bonuses = cur.execute(
        "SELECT COUNT(*) FROM wallet_transactions w WHERE w.game_name = 'Weekly Loss Bonus' "
        "AND EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id AND b.matched_category = 'Weekly Loss Bonus')"
    ).fetchone()[0]
    print(f"  wallet_transactions rows: {total_wt}, classified into bonuses table: {matched_in_bonuses}, MISSING: {total_wt - matched_in_bonuses}")

    print("=== sample of 'Weekly Loss Bonus' rows that did NOT make it into bonuses (source, source_id shown) ===")
    for row in cur.execute(
        "SELECT w.id, w.user_id, w.source, w.source_id, w.create_time FROM wallet_transactions w "
        "WHERE w.game_name = 'Weekly Loss Bonus' "
        "AND NOT EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id) "
        "ORDER BY w.create_time DESC LIMIT 15"
    ).fetchall():
        print(" ", row)

    conn.close()


if __name__ == "__main__":
    main()
