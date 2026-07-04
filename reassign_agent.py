"""
Reassign (or unassign) a single user's calling agent. Runs inside GitHub
Actions, triggered by the "Reassign Agent" widget on the dashboard's Search
User page (via the master-userlist-upload worker's /reassign-agent endpoint).

Downloads master_userlist.db from R2, upserts (or deletes, for un-assign)
one row in agent_assignments, and re-uploads -- the same read-modify-write
pattern ci_ingest.py uses for bulk file ingests, just scoped to one user_id
instead of a whole spreadsheet.

Usage: python3 reassign_agent.py --user-id 12345 --agent "Sathya (WFH)"
       python3 reassign_agent.py --user-id 12345 --agent ""   (un-assign)
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
    ap.add_argument("--agent", required=True, help="Agent name, or empty string to un-assign")
    args = ap.parse_args()

    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()

    try:
        s3.download_file(bucket, "master_userlist.db", MASTER_DB)
        # Not modified here, but build_deposit_report.py (run right after this
        # script, in the same job workspace) needs it present locally to
        # refresh the live report -- same download-both-DBs pattern ci_ingest.py
        # uses, just for a script that only writes to one of them.
        s3.download_file(bucket, "daily_records.db", DAILY_DB)
    except Exception as e:
        print(f"FATAL: could not download DBs from R2: {e}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(MASTER_DB)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS agent_assignments (user_id INTEGER PRIMARY KEY, agent_name TEXT)")

    exists = cur.execute("SELECT 1 FROM users WHERE user_id = ?", (args.user_id,)).fetchone()
    if not exists:
        print(f"FATAL: user_id {args.user_id} not found in users table", file=sys.stderr)
        conn.close()
        sys.exit(1)

    agent = args.agent.strip()
    if agent:
        cur.execute(
            "INSERT OR REPLACE INTO agent_assignments (user_id, agent_name) VALUES (?, ?)",
            (args.user_id, agent),
        )
        print(f"Assigned user {args.user_id} -> {agent}")
    else:
        cur.execute("DELETE FROM agent_assignments WHERE user_id = ?", (args.user_id,))
        print(f"Un-assigned user {args.user_id}")
    conn.commit()
    conn.close()

    s3.upload_file(MASTER_DB, bucket, "master_userlist.db")
    print("Uploaded updated master_userlist.db")


if __name__ == "__main__":
    main()
