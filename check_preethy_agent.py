"""One-off read-only check: find the exact stored agent_name(s) matching
"Preethy" (case-insensitive, any suffix like "(WFH)"), how many users are
assigned, whether agent_performance has historical rows for them, and
whether a custom password override exists -- before writing a rename
migration.

Usage: python3 check_preethy_agent.py
"""
import os
import sqlite3

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
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    s3.download_file(bucket, "master_userlist.db", MASTER_DB)

    conn = sqlite3.connect(MASTER_DB)
    cur = conn.cursor()

    print("=== Distinct agent_name values in agent_assignments matching 'preethy' (case-insensitive) ===")
    for row in cur.execute(
        "SELECT agent_name, COUNT(*) FROM agent_assignments WHERE agent_name LIKE '%preethy%' COLLATE NOCASE GROUP BY agent_name"
    ).fetchall():
        print(" ", row)

    print("=== All distinct agent_name values currently in agent_assignments (for naming-convention reference) ===")
    for row in cur.execute("SELECT DISTINCT agent_name FROM agent_assignments ORDER BY agent_name").fetchall():
        print(" ", row)

    print("=== agent_performance: distinct agent_name values matching 'preethy' ===")
    try:
        for row in cur.execute(
            "SELECT agent_name, COUNT(*) FROM agent_performance WHERE agent_name LIKE '%preethy%' COLLATE NOCASE GROUP BY agent_name"
        ).fetchall():
            print(" ", row)
    except sqlite3.OperationalError as e:
        print("  (agent_performance check failed:", e, ")")

    print("=== Check if 'Aarthy' already exists as an agent anywhere ===")
    for row in cur.execute(
        "SELECT agent_name, COUNT(*) FROM agent_assignments WHERE agent_name LIKE '%aarthy%' COLLATE NOCASE GROUP BY agent_name"
    ).fetchall():
        print(" ", row)

    conn.close()

    print("=== config/agent_password_overrides.json ===")
    try:
        obj = s3.get_object(Bucket=bucket, Key="config/agent_password_overrides.json")
        import json
        overrides = json.loads(obj["Body"].read())
        print(" ", overrides)
    except Exception as e:
        print("  (no overrides file or read failed:", e, ")")


if __name__ == "__main__":
    main()
