"""
Removes a user from the permanent banned_users table so they stop being
purged on every future ingestion run (see ban_utils.py / ban_user.py).

IMPORTANT: this does NOT restore anything that was already deleted when the
user was banned. ban_user.py permanently deletes their users/
agent_assignments/balance_adjustments rows in master_userlist.db and their
deposits/withdrawals/wallet_transactions/bonuses rows in daily_records.db
at the moment of banning -- there's no soft-delete/backup, so that history
is gone. This script only stops FUTURE purging; whatever the business API's
regular rolling-window pulls (deposits: ~5 days, withdrawals: ~5 days,
wallet: current export) pick up for this user_id from now on will
re-populate their profile from scratch, same as a brand-new user.

Usage: python3 unban_user.py --user-id 1162645
"""
import argparse
import os
import sqlite3
import sys

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", required=True, type=int)
    args = ap.parse_args()

    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    try:
        s3.download_file(bucket, "master_userlist.db", MASTER_DB)
    except Exception as e:
        print(f"FATAL: could not download master_userlist.db from R2: {e}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(MASTER_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY, banned_at TEXT)")
    row = conn.execute("SELECT banned_at FROM banned_users WHERE user_id = ?", (args.user_id,)).fetchone()
    if row is None:
        print(f"user_id {args.user_id} was not in banned_users -- nothing to remove")
    else:
        conn.execute("DELETE FROM banned_users WHERE user_id = ?", (args.user_id,))
        conn.commit()
        print(f"Removed user_id {args.user_id} from banned_users (was banned at {row[0]})")
    conn.close()

    s3.upload_file(MASTER_DB, bucket, "master_userlist.db")
    print("Uploaded master_userlist.db")


if __name__ == "__main__":
    main()
