"""Verify the Weekly Loss Bonus casing merge landed after pipeline run 30736983152."""
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

    print("=== bonuses: matched_category LIKE '%Weekly Loss%' -- distinct categories + counts ===")
    for row in cur.execute(
        "SELECT matched_category, COUNT(*) FROM bonuses WHERE matched_category LIKE '%Weekly Loss%' "
        "GROUP BY matched_category ORDER BY COUNT(*) DESC LIMIT 30"
    ).fetchall():
        print(" ", row)

    print("=== per-user distinct matched_category count for the previously-split users ===")
    for uid in (1879887, 1855688, 1718590, 1665154):
        rows = cur.execute(
            "SELECT DISTINCT matched_category FROM bonuses WHERE user_id = ? AND matched_category LIKE '%Weekly Loss%'",
            (uid,),
        ).fetchall()
        print(f"  user {uid}: {[r[0] for r in rows]}")

    print("=== backfill_state ===")
    for row in cur.execute("SELECT key, value FROM backfill_state").fetchall():
        print(" ", row)

    conn.close()


if __name__ == "__main__":
    main()
