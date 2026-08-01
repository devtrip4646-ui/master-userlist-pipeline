"""One-off read-only check: is wallet_transactions.source_id a stable,
already-unique identifier we could use for dedup instead of the numeric
`id` column (which we've confirmed resets monthly and collides with the
same day one month prior)? Compare source_id for a handful of today's rows
against the same id positions from a month ago.
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

    print("=== sample rows for 2026-08-01 (id, source_id, create_time) ===")
    for row in cur.execute(
        "SELECT id, source_id, create_time FROM wallet_transactions "
        "WHERE create_time >= '2026-08-01' ORDER BY create_time DESC LIMIT 10"
    ).fetchall():
        print(" ", row)

    print("=== sample rows for 2026-07-01 near id 300000-300010 (id, source_id, create_time) ===")
    for row in cur.execute(
        "SELECT id, source_id, create_time FROM wallet_transactions "
        "WHERE id BETWEEN 300000 AND 300010 ORDER BY id LIMIT 10"
    ).fetchall():
        print(" ", row)

    print("=== COUNT(DISTINCT source_id) vs COUNT(*) overall (is source_id unique?) ===")
    print(" ", cur.execute("SELECT COUNT(*), COUNT(DISTINCT source_id) FROM wallet_transactions").fetchone())

    print("=== source_id NULL/blank count ===")
    print(" ", cur.execute("SELECT COUNT(*) FROM wallet_transactions WHERE source_id IS NULL OR source_id = ''").fetchone())

    conn.close()


if __name__ == "__main__":
    main()
