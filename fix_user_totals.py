"""
One-off correction script for a user_id whose users.total_recharge /
total_withdrawal / user_balance are confirmed wrong against the platform's
own records -- see ingest_userlist()'s fix in ingest_update.py for the
systemic bug (a one-time historical double-count of deposits/withdrawals,
baked in the first time deposit_sync_time/withdrawal_sync_time were added)
this compensates for on specific already-affected accounts. Run manually via
GitHub Actions when a user reports a specific, verified discrepancy.

Usage: python3 fix_user_totals.py --user-id 1761219 --balance 355087.25 \
    --total-recharge 1334006 --total-withdrawal 1361000
"""
import argparse
import os
import sqlite3
import sys

import boto3

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
    ap.add_argument("--balance", required=True, type=float)
    ap.add_argument("--total-recharge", required=True, type=float)
    ap.add_argument("--total-withdrawal", required=True, type=float)
    args = ap.parse_args()

    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    try:
        s3.download_file(bucket, "master_userlist.db", MASTER_DB)
        # Not modified here, but build_deposit_report.py (run right after
        # this script, in the same job workspace) needs it present locally
        # to refresh the live report -- same pattern as reassign_agent.py.
        s3.download_file(bucket, "daily_records.db", DAILY_DB)
    except Exception as e:
        print(f"FATAL: could not download DBs from R2: {e}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(MASTER_DB)
    cur = conn.cursor()
    row = cur.execute(
        "SELECT user_balance, total_recharge, total_withdrawal FROM users WHERE user_id = ?", (args.user_id,)
    ).fetchone()
    if row is None:
        print(f"FATAL: user_id {args.user_id} not found in users table", file=sys.stderr)
        conn.close()
        sys.exit(1)

    print(f"Before: user_balance={row[0]}, total_recharge={row[1]}, total_withdrawal={row[2]}")
    cur.execute(
        "UPDATE users SET user_balance = ?, total_recharge = ?, total_withdrawal = ? WHERE user_id = ?",
        (args.balance, args.total_recharge, args.total_withdrawal, args.user_id),
    )
    conn.commit()
    conn.close()

    s3.upload_file(MASTER_DB, bucket, "master_userlist.db")
    print(f"After:  user_balance={args.balance}, total_recharge={args.total_recharge}, total_withdrawal={args.total_withdrawal}")
    print(f"Corrected user {args.user_id} and uploaded master_userlist.db")


if __name__ == "__main__":
    main()
