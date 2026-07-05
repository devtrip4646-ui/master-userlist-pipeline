"""
Records a manual balance correction as an actual wallet_transactions row
(instead of just patching users.user_balance directly, like
fix_user_totals.py does) -- so the deduction survives the next
sync_master_userlist() run (api_pull_ingest.py), which recomputes
user_balance from wallet_transactions.change_after for every user with
wallet activity and would otherwise silently overwrite a direct
users.user_balance patch back to the (still ledger-derived) value.

The synthetic row uses a large negative id (never collides with real
source-system ids, which are always positive) and create_time set to just
after the user's true latest transaction, so it sorts as the newest row via
the same (create_time, id) tie-break resync_user_balances.py/
api_pull_ingest.py use, and change_after (current_balance - amount) becomes
the new user_balance on the very next sync -- no special-casing needed
elsewhere.

Usage: python3 manual_wallet_deduct.py --user-id 1761219 --amount 20000 \
    --reason "Manual deduction: unexplained wallet ledger gap"
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta

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
    ap.add_argument("--amount", required=True, type=float, help="Positive amount to deduct")
    ap.add_argument("--reason", default="Manual deduct")
    args = ap.parse_args()

    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    try:
        s3.download_file(bucket, "master_userlist.db", MASTER_DB)
        s3.download_file(bucket, "daily_records.db", DAILY_DB)
    except Exception as e:
        print(f"FATAL: could not download DBs from R2: {e}", file=sys.stderr)
        sys.exit(1)

    dconn = sqlite3.connect(DAILY_DB)
    dcur = dconn.cursor()
    row = dcur.execute(
        "SELECT change_after, create_time, id FROM wallet_transactions "
        "WHERE user_id = ? ORDER BY create_time DESC, id DESC LIMIT 1",
        (args.user_id,),
    ).fetchone()
    if row is None or row[0] is None:
        print(f"FATAL: no wallet_transactions rows with a balance found for user {args.user_id}", file=sys.stderr)
        sys.exit(1)
    current_balance, last_create_time, last_id = row
    new_balance = round(current_balance - args.amount, 2)
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    new_create_time = now.strftime("%Y-%m-%d %H:%M:%S")

    print(f"Latest ledger row for user {args.user_id}: change_after={current_balance}, create_time={last_create_time}, id={last_id}")
    print(f"Inserting manual deduction of {args.amount} -> new change_after={new_balance}")

    synthetic_id = -int(now.timestamp() * 1000)
    dcur.execute(
        "INSERT INTO wallet_transactions "
        "(id, game_name, user_id, consume_type, direction, change_value, change_after, "
        "change_desc, source_id, user_phone, table_name, create_date, source, "
        "tripartite_uniqueness, l1_category_id, l2_category_id, status, create_time, "
        "update_time, package_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            synthetic_id, None, args.user_id, "manual_deduct", 1, args.amount, new_balance,
            None, args.reason, None, None, None, "manual_adjustment",
            None, None, None, "COMPLETE", new_create_time, new_create_time, None,
        ),
    )
    dconn.commit()
    dconn.close()

    mconn = sqlite3.connect(MASTER_DB)
    mcur = mconn.cursor()
    urow = mcur.execute("SELECT user_balance FROM users WHERE user_id = ?", (args.user_id,)).fetchone()
    if urow is None:
        print(f"FATAL: user_id {args.user_id} not found in master_userlist.db users table", file=sys.stderr)
        sys.exit(1)
    print(f"Before: user_balance={urow[0]}")
    mcur.execute("UPDATE users SET user_balance = ? WHERE user_id = ?", (new_balance, args.user_id))
    mconn.commit()
    mconn.close()
    print(f"After:  user_balance={new_balance}")

    s3.upload_file(DAILY_DB, bucket, "daily_records.db")
    s3.upload_file(MASTER_DB, bucket, "master_userlist.db")
    print(f"Recorded manual deduction transaction (id={synthetic_id}) and uploaded both DBs")


if __name__ == "__main__":
    main()
