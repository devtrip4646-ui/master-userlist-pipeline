"""
Removes an agent name that has no users currently assigned to them --
the inverse of create_agent.py. Refuses (does not cascade-unassign) if the
agent still has any agent_assignments rows, since silently moving their
users to Un-Assigned would be a surprising side effect of what looks like
a pure roster cleanup action; the admin should reassign those users first
via the existing Reassign Agent feature, then remove the now-empty agent.

Deletes the agent_roster row (if any) and any config/agent_password_overrides.json
entry for them (hygiene -- harmless to leave, but pointless once the agent
is gone). Does NOT touch agent_performance -- that table is keyed purely on
agent_name TEXT with no foreign key, so historical Performance-page rows for
a removed agent survive untouched, same as after a rename (see
rename_agent.py).

Triggered by the "Remove Agent" widget on the master-userlist-upload
worker's page (via its /remove-agent endpoint) -- same pattern as
create_agent.py / rename_agent.py.

Usage: python3 remove_agent.py --agent-name "Priya (WFH)"
"""
import argparse
import json
import os
import sys

import boto3
import sqlite3

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
    ap.add_argument("--agent-name", required=True)
    args = ap.parse_args()

    agent_name = args.agent_name.strip()
    if not agent_name:
        print("FATAL: agent name is empty", file=sys.stderr)
        sys.exit(1)
    if agent_name == "Un-Assigned":
        print('FATAL: "Un-Assigned" is a reserved label, not a real agent', file=sys.stderr)
        sys.exit(1)

    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    try:
        s3.download_file(bucket, "master_userlist.db", MASTER_DB)
        # Not modified here, but build_deposit_report.py (run right after
        # this script, in the same job workspace, since remove_agent.yml --
        # like create_agent.yml -- refreshes the report synchronously)
        # needs it present locally. Same pattern as create_agent.py.
        s3.download_file(bucket, "daily_records.db", DAILY_DB)
    except Exception as e:
        print(f"FATAL: could not download DBs from R2: {e}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(MASTER_DB)
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS agent_roster (agent_name TEXT PRIMARY KEY, created_at TEXT)")

    assignment_count = cur.execute(
        "SELECT COUNT(*) FROM agent_assignments WHERE agent_name = ?", (agent_name,)
    ).fetchone()[0]
    if assignment_count > 0:
        conn.close()
        print(
            f"FATAL: '{agent_name}' still has {assignment_count} user(s) assigned -- "
            "reassign them to another agent (or Un-Assigned) first, then remove",
            file=sys.stderr,
        )
        sys.exit(1)

    in_roster = cur.execute("SELECT 1 FROM agent_roster WHERE agent_name = ?", (agent_name,)).fetchone()
    if not in_roster:
        conn.close()
        print(f"NOTE: agent '{agent_name}' isn't in the roster and has no assigned users -- nothing to remove")
        return

    cur.execute("DELETE FROM agent_roster WHERE agent_name = ?", (agent_name,))
    conn.commit()
    conn.close()

    s3.upload_file(MASTER_DB, bucket, "master_userlist.db")
    print(f"Removed agent '{agent_name}' from the roster -- will disappear after the next report refresh")

    try:
        obj = s3.get_object(Bucket=bucket, Key="config/agent_password_overrides.json")
        overrides = json.loads(obj["Body"].read())
    except Exception:
        overrides = {}

    if agent_name in overrides:
        del overrides[agent_name]
        s3.put_object(
            Bucket=bucket, Key="config/agent_password_overrides.json",
            Body=json.dumps(overrides).encode("utf-8"), ContentType="application/json",
        )
        print(f"Removed leftover password override for '{agent_name}'")


if __name__ == "__main__":
    main()
