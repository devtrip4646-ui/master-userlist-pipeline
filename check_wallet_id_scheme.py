"""One-off read-only check: is wallet_transactions.id a stable, globally
increasing counter, or does it look like it resets/overlaps across days?
Today's bonus rows (ids ~325671-361408) are far lower than yesterday's
(~42.9 million) -- if id ranges overlap across different create_time dates,
that would explain "Wallet transactions: 0 rows added" despite the source
export's byte size clearly growing each run: INSERT OR IGNORE silently
discards genuinely-new transactions because their id collides with an
already-ingested row from a different day.

Usage: python3 check_wallet_id_scheme.py
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

    print("=== wallet_transactions: overall MIN(id) / MAX(id) / COUNT(*) ===")
    print(" ", cur.execute("SELECT MIN(id), MAX(id), COUNT(*) FROM wallet_transactions").fetchone())

    print("=== wallet_transactions: MIN(id)/MAX(id)/COUNT(*) by create_time date, last 5 days ===")
    for row in cur.execute(
        "SELECT substr(create_time,1,10) AS d, MIN(id), MAX(id), COUNT(*) FROM wallet_transactions "
        "WHERE create_time >= date('now', '-5 days') GROUP BY d ORDER BY d"
    ).fetchall():
        print(" ", row)

    print("=== bonuses: MIN(id)/MAX(id)/COUNT(*) by create_time date, last 5 days ===")
    for row in cur.execute(
        "SELECT substr(create_time,1,10) AS d, MIN(id), MAX(id), COUNT(*) FROM bonuses "
        "WHERE create_time >= date('now', '-5 days') GROUP BY d ORDER BY d"
    ).fetchall():
        print(" ", row)

    print("=== what currently exists at id=325671, 355750, 361408 (today's 3 bonus rows) ===")
    for target_id in (325671, 355750, 361408):
        rows = cur.execute(
            "SELECT id, game_name, user_id, change_value, create_time FROM wallet_transactions WHERE id = ?",
            (target_id,),
        ).fetchall()
        print(f"  id={target_id}:", rows)

    print("=== sample of 10 wallet_transactions rows with id BETWEEN 300000 and 400000, any date ===")
    for row in cur.execute(
        "SELECT id, game_name, user_id, create_time FROM wallet_transactions "
        "WHERE id BETWEEN 300000 AND 400000 ORDER BY id LIMIT 10"
    ).fetchall():
        print(" ", row)

    print("=== how many DISTINCT dates share overlapping id ranges (potential collision check) ===")
    print("  (min/max id per date printed above -- inspect manually for overlap)")

    conn.close()


if __name__ == "__main__":
    main()
