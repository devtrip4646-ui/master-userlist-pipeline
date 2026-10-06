"""One-off migration: rename an agent everywhere their name is stored --
agent_assignments (every assigned user), agent_performance (historical
rows, so Performance page history survives the rename instead of being
orphaned), and config/agent_password_overrides.json (so the same login
password keeps working under the new name). Unlike reassign_agent.py
(which moves specific USER IDs to a DIFFERENT existing agent), this
renames the AGENT ENTITY itself -- every user stays with the same agent,
just under the corrected name.

Also renames the agent_roster entry (so the old name doesn't linger in the
agent list), and refuses if the new name already exists. With
--reset-password the old name's custom login password override is dropped
instead of carried forward, so the agent gets the default password derived
from their NEW name.

Usage: python3 rename_agent.py --from "Preethy (WFH)" --to "Aarthy (WFH)" [--reset-password]
"""
import argparse
import json
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
    ap.add_argument("--from", dest="from_name", required=True, help="Exact current agent_name")
    ap.add_argument("--to", dest="to_name", required=True, help="Exact new agent_name")
    ap.add_argument("--reset-password", action="store_true",
                    help="Drop the old name's custom password override instead of carrying it to the new name")
    args = ap.parse_args()

    from_name, to_name = args.from_name.strip(), args.to_name.strip()
    if from_name == to_name:
        print("FATAL: --from and --to are identical, nothing to do", file=sys.stderr)
        sys.exit(1)

    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()

    try:
        s3.download_file(bucket, "master_userlist.db", MASTER_DB)
    except Exception as e:
        print(f"FATAL: could not download master_userlist.db from R2: {e}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(MASTER_DB)
    cur = conn.cursor()

    cur.execute("CREATE TABLE IF NOT EXISTS agent_roster (agent_name TEXT PRIMARY KEY, created_at TEXT)")
    assignment_count = cur.execute(
        "SELECT COUNT(*) FROM agent_assignments WHERE agent_name = ?", (from_name,)
    ).fetchone()[0]
    roster_row = cur.execute(
        "SELECT created_at FROM agent_roster WHERE agent_name = ?", (from_name,)
    ).fetchone()
    if assignment_count == 0 and roster_row is None:
        print(f"FATAL: {from_name!r} has no agent_assignments rows and isn't in the roster -- nothing to rename", file=sys.stderr)
        sys.exit(1)

    # Refuse to merge into an agent that already exists -- a rename should
    # never silently fold two agents' users together.
    to_assigned = cur.execute("SELECT COUNT(*) FROM agent_assignments WHERE agent_name = ?", (to_name,)).fetchone()[0]
    to_in_roster = cur.execute("SELECT 1 FROM agent_roster WHERE agent_name = ?", (to_name,)).fetchone()
    if to_assigned or to_in_roster:
        print(f"FATAL: {to_name!r} already exists as an agent -- refusing to rename onto it", file=sys.stderr)
        sys.exit(1)

    # Guard against a PK collision: agent_performance's primary key is
    # (date, agent_name, category) -- if `to_name` already has performance
    # rows for the same (date, category) as `from_name`, a blind UPDATE
    # would violate that constraint. Confirmed via diagnostic that "Aarthy"
    # doesn't exist as an agent at all yet, but check again here so this
    # script is safe to reuse for a future rename where the target name
    # might already exist.
    collisions = cur.execute(
        "SELECT COUNT(*) FROM agent_performance a WHERE a.agent_name = ? AND EXISTS ("
        "  SELECT 1 FROM agent_performance b WHERE b.agent_name = ? AND b.date = a.date AND b.category = a.category"
        ")",
        (from_name, to_name),
    ).fetchone()[0]
    if collisions:
        print(
            f"FATAL: {to_name!r} already has {collisions} overlapping agent_performance row(s) "
            f"with {from_name!r} -- refusing to rename, would violate the (date, agent_name, category) primary key",
            file=sys.stderr,
        )
        sys.exit(1)

    cur.execute("UPDATE agent_assignments SET agent_name = ? WHERE agent_name = ?", (to_name, from_name))
    reassigned = cur.rowcount

    if roster_row is not None:
        cur.execute("INSERT INTO agent_roster (agent_name, created_at) VALUES (?, ?)", (to_name, roster_row[0]))
        cur.execute("DELETE FROM agent_roster WHERE agent_name = ?", (from_name,))

    perf_updated = 0
    try:
        cur.execute("UPDATE agent_performance SET agent_name = ? WHERE agent_name = ?", (to_name, from_name))
        perf_updated = cur.rowcount
    except sqlite3.OperationalError:
        pass  # table doesn't exist yet -- nothing to carry over

    conn.commit()
    conn.close()

    print(f"Renamed agent {from_name!r} -> {to_name!r}: {reassigned} user(s) in agent_assignments, "
          f"{perf_updated} historical agent_performance row(s)")

    s3.upload_file(MASTER_DB, bucket, "master_userlist.db")
    print("Uploaded updated master_userlist.db")

    # Carry the password override forward under the new name too, so the
    # same login credential keeps working -- a rename shouldn't force the
    # agent to learn a new password. Only touches the override file if one
    # actually exists for from_name; otherwise leaves it alone (the agent
    # was using the auto-derived default, which will now auto-derive from
    # the new name instead -- also fine, just a different default).
    try:
        obj = s3.get_object(Bucket=bucket, Key="config/agent_password_overrides.json")
        overrides = json.loads(obj["Body"].read())
    except Exception:
        overrides = {}

    if args.reset_password:
        dropped = [n for n in (from_name, to_name) if n in overrides]
        for n in dropped:
            del overrides[n]
        if dropped:
            s3.put_object(
                Bucket=bucket, Key="config/agent_password_overrides.json",
                Body=json.dumps(overrides).encode("utf-8"), ContentType="application/json",
            )
        print(f"Password reset: dropped override(s) for {dropped or 'none (none existed)'} -- "
              f"{to_name!r} now uses the default password derived from the new name")
    elif from_name in overrides:
        overrides[to_name] = overrides.pop(from_name)
        s3.put_object(
            Bucket=bucket, Key="config/agent_password_overrides.json",
            Body=json.dumps(overrides).encode("utf-8"), ContentType="application/json",
        )
        print(f"Carried password override forward: {to_name!r} keeps the same login password {from_name!r} had")
    else:
        print(f"No password override existed for {from_name!r} -- nothing to carry forward")


if __name__ == "__main__":
    main()
