"""One-off read-only check (v2): "Weekly Loss Bonus" is not a game_name in
wallet_transactions (confirmed: zero matches). Check whether it comes
through via source_id instead, the same way "Daily Active Bonus" does --
classify_bonus()'s rule 3 only normalizes source_id text that starts with
"daily active bonus"/"daily active bonus low"; any OTHER source_id
containing the word "bonus" (e.g. "Weekly Loss Bonus-<random hex>") falls
through to `return source_id` UNNORMALIZED, meaning each instance gets a
different matched_category (the random suffix included) instead of one
clean rolled-up label -- which would explain why it looks
present/inconsistent across users.
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

    print("=== wallet_transactions: source_id LIKE '%Weekly Loss%' -- total count ===")
    print(" ", cur.execute("SELECT COUNT(*) FROM wallet_transactions WHERE source_id LIKE '%Weekly Loss%'").fetchone()[0])

    print("=== sample of 15 such rows (id, user_id, game_name, source, source_id, create_time) ===")
    for row in cur.execute(
        "SELECT id, user_id, game_name, source, source_id, create_time FROM wallet_transactions "
        "WHERE source_id LIKE '%Weekly Loss%' ORDER BY create_time DESC LIMIT 15"
    ).fetchall():
        print(" ", row)

    print("=== bonuses table: matched_category LIKE '%Weekly Loss%' -- distinct categories + counts ===")
    for row in cur.execute(
        "SELECT matched_category, COUNT(*) FROM bonuses WHERE matched_category LIKE '%Weekly Loss%' "
        "GROUP BY matched_category ORDER BY COUNT(*) DESC LIMIT 30"
    ).fetchall():
        print(" ", row)

    print("=== how many 'Weekly Loss' source_id wallet_transactions rows made it into bonuses at all ===")
    total_wt = cur.execute("SELECT COUNT(*) FROM wallet_transactions WHERE source_id LIKE '%Weekly Loss%'").fetchone()[0]
    in_bonuses = cur.execute(
        "SELECT COUNT(*) FROM wallet_transactions w WHERE w.source_id LIKE '%Weekly Loss%' "
        "AND EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id)"
    ).fetchone()[0]
    print(f"  wallet_transactions rows: {total_wt}, present in bonuses (any category): {in_bonuses}, MISSING: {total_wt - in_bonuses}")

    print("=== of those NOT in bonuses, sample game_name/source (why classify_bonus rejected them) ===")
    for row in cur.execute(
        "SELECT w.id, w.user_id, w.game_name, w.source, w.source_id, w.create_time FROM wallet_transactions w "
        "WHERE w.source_id LIKE '%Weekly Loss%' AND NOT EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id) "
        "ORDER BY w.create_time DESC LIMIT 15"
    ).fetchall():
        print(" ", row)

    print("=== per-user distinct matched_category count for users who have ANY 'Weekly Loss' bonus row ===")
    for row in cur.execute(
        "SELECT w.user_id, COUNT(DISTINCT b.matched_category) AS distinct_cats, COUNT(*) AS n "
        "FROM wallet_transactions w JOIN bonuses b ON b.id = w.id "
        "WHERE w.source_id LIKE '%Weekly Loss%' GROUP BY w.user_id ORDER BY n DESC LIMIT 10"
    ).fetchall():
        print(" ", row)

    conn.close()


if __name__ == "__main__":
    main()
