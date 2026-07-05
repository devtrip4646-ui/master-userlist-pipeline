"""
Bans a user: deletes every trace of their records (users, agent_assignments,
balance_adjustments in master_userlist.db; deposits, withdrawals,
wallet_transactions, bonuses in daily_records.db) and adds them to the
permanent banned_users table so they can never reappear, even if the
business platform sends new deposit/withdrawal/wallet activity for that
user_id in a future hourly pull -- see ban_utils.py, imported by both
ingest_update.py (purges on every ingestion run) and api_pull_ingest.py's
sync_master_userlist() (never re-inserts a banned user_id).

Triggered by the "Ban User" widget on the dashboard's Search User page (via
the master-userlist-upload worker's /ban-user endpoint) -- same pattern as
reassign_agent.py.

Usage: python3 ban_user.py --user-id 12345
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta

import boto3

import ban_utils

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", required=True, type=int)
    args = ap.parse_args()

    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    try:
        s3.download_file(bucket, "master_userlist.db", MASTER_DB)
        s3.download_file(bucket, "daily_records.db", DAILY_DB)
    except Exception as e:
        print(f"FATAL: could not download DBs from R2: {e}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(MASTER_DB)
    exists = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (args.user_id,)).fetchone()
    conn.execute("CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY, banned_at TEXT)")
    now = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO banned_users (user_id, banned_at) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET banned_at = excluded.banned_at",
        (args.user_id, now),
    )
    conn.commit()
    conn.close()
    if not exists:
        print(f"NOTE: user_id {args.user_id} was not found in users table (banning anyway, in case only daily_records has traces)")

    master_touched, daily_touched = ban_utils.purge_banned_users(MASTER_DB, DAILY_DB)
    print(f"Banned user {args.user_id} at {now} -- master_touched={master_touched}, daily_touched={daily_touched}")

    s3.upload_file(MASTER_DB, bucket, "master_userlist.db")
    s3.upload_file(DAILY_DB, bucket, "daily_records.db")
    print("Uploaded both DBs")


if __name__ == "__main__":
    main()
