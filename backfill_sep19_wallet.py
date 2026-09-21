"""One-off backfill: the automated wallet pull for 2026-09-19 apparently
never happened (bonuses table shows zero rows for that whole day, despite
every other day being normal), so the user manually exported that day's
wallet_transactions detail sheet from the business admin panel and uploaded
it to R2 at manual_uploads/detail_20260919_manual.xlsx. This downloads the
current daily_records.db, ingests that file through the normal
ingest_wallet() path (same classification logic as the regular hourly
pipeline -- INSERT OR IGNORE on id, so re-running this is a safe no-op),
checks whether New Users Lossback bonuses for that day now classify
correctly, and uploads the updated db back to R2. One-off; delete this
script and its workflow after use.
"""
import json
import os
import sqlite3
import sys

import boto3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest_update

BASE = os.path.dirname(os.path.abspath(__file__))
MANUAL_XLSX = os.path.join(BASE, "detail_20260919_manual.xlsx")


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

    print("Downloading current daily_records.db...")
    s3.download_file(bucket, "daily_records.db", ingest_update.DAILY_DB)

    print("Downloading manual wallet export from R2...")
    s3.download_file(bucket, "manual_uploads/detail_20260919_manual.xlsx", MANUAL_XLSX)

    before = sqlite3.connect(ingest_update.DAILY_DB).execute(
        "SELECT COUNT(*) FROM bonuses WHERE matched_category = 'New Users Lossback' "
        "AND substr(create_time,1,10) = '2026-09-19'"
    ).fetchone()[0]
    print(f"New Users Lossback bonus rows for 2026-09-19 BEFORE ingest: {before}")

    print("Ingesting manual wallet file...")
    ingest_update.ingest_wallet([MANUAL_XLSX])

    conn = sqlite3.connect(ingest_update.DAILY_DB)
    after = conn.execute(
        "SELECT COUNT(*) FROM bonuses WHERE matched_category = 'New Users Lossback' "
        "AND substr(create_time,1,10) = '2026-09-19'"
    ).fetchone()[0]
    print(f"New Users Lossback bonus rows for 2026-09-19 AFTER ingest: {after}")

    total_bonuses_that_day = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(change_value),0) FROM bonuses WHERE substr(create_time,1,10) = '2026-09-19'"
    ).fetchone()
    print(f"Total bonus rows for 2026-09-19 (all categories): count={total_bonuses_that_day[0]} sum={total_bonuses_that_day[1]}")

    if after == 0:
        print("Still zero -- dumping raw game_name/source_id groupings for that day to debug:")
        groups = conn.execute(
            "SELECT game_name, source, COUNT(*) FROM wallet_transactions "
            "WHERE substr(create_time,1,10) = '2026-09-19' AND source_id LIKE 'New Users Lossback%' "
            "GROUP BY game_name, source"
        ).fetchall()
        print(json.dumps(groups, default=str, indent=2))

    fd_count = conn.execute(
        "SELECT COUNT(DISTINCT user_id) FROM deposits WHERE status='COMPLETE' AND is_first_deposit=1 "
        "AND substr(create_time,1,10)='2026-09-19'"
    ).fetchone()[0]
    print(f"FD users for 2026-09-19 (sanity check, should be 681): {fd_count}")

    conn.close()

    print("Uploading updated daily_records.db back to R2...")
    s3.upload_file(ingest_update.DAILY_DB, bucket, "daily_records.db")
    print("Done.")


if __name__ == "__main__":
    main()
