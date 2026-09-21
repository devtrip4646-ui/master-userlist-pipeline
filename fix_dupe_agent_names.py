"""One-off migration: merge duplicate agent_name spellings caused by
inconsistent spacing in a spreadsheet header ("Lakshmi( WFH)" vs
"Lakshmi (WFH)", "Reetu( WFH)" vs "Reetu (WFH)") into a single canonical
name each, in both agent_assignments and agent_roster, then regenerates
reports/agent_list.json so the dashboard's Agent Logins list stops showing
two rows (with the same formula-derived password) for the same person.

Always writes debug/fix_dupe_agent_names.json (including a traceback on
failure) and commits it, since GitHub Actions logs for this repo aren't
readable without signing in -- that's the only way to see what happened.
One-off; delete this script and its workflow after use.
"""
import json
import os
import sqlite3
import subprocess
import traceback

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")

RENAMES = {
    "Lakshmi( WFH)": "Lakshmi (WFH)",
    "Reetu( WFH)": "Reetu (WFH)",
}


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def run_migration(result):
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()

    s3.download_file(bucket, "master_userlist.db", MASTER_DB)
    conn = sqlite3.connect(MASTER_DB)
    cur = conn.cursor()

    result["all_agent_names_before"] = sorted(
        r[0] for r in cur.execute("SELECT DISTINCT agent_name FROM agent_assignments").fetchall()
    )

    result["renames"] = {}
    for bad, good in RENAMES.items():
        n_assign = cur.execute(
            "SELECT COUNT(*) FROM agent_assignments WHERE agent_name = ?", (bad,)
        ).fetchone()[0]
        cur.execute(
            "UPDATE agent_assignments SET agent_name = ? WHERE agent_name = ?", (good, bad)
        )
        n_roster = 0
        try:
            n_roster = cur.execute(
                "SELECT COUNT(*) FROM agent_roster WHERE agent_name = ?", (bad,)
            ).fetchone()[0]
            if n_roster:
                created_at = cur.execute(
                    "SELECT created_at FROM agent_roster WHERE agent_name = ?", (bad,)
                ).fetchone()[0]
                cur.execute(
                    "INSERT OR IGNORE INTO agent_roster (agent_name, created_at) VALUES (?, ?)",
                    (good, created_at),
                )
                cur.execute("DELETE FROM agent_roster WHERE agent_name = ?", (bad,))
        except sqlite3.OperationalError as e:
            result["renames"].setdefault("agent_roster_errors", []).append(str(e))
        result["renames"][bad] = {"good": good, "agent_assignments_rows": n_assign, "agent_roster_rows": n_roster}

    conn.commit()

    result["all_agent_names_after"] = sorted(
        r[0] for r in cur.execute("SELECT DISTINCT agent_name FROM agent_assignments").fetchall()
    )
    conn.close()

    s3.upload_file(MASTER_DB, bucket, "master_userlist.db")

    # Clean up any admin-set password override stored under the bad spelling.
    try:
        obj = s3.get_object(Bucket=bucket, Key="config/agent_password_overrides.json")
        overrides = json.loads(obj["Body"].read())
        changed = False
        for bad, good in RENAMES.items():
            if bad in overrides:
                overrides.setdefault(good, overrides.pop(bad))
                changed = True
        if changed:
            s3.put_object(
                Bucket=bucket,
                Key="config/agent_password_overrides.json",
                Body=json.dumps(overrides).encode(),
            )
        result["overrides_after"] = overrides
    except s3.exceptions.NoSuchKey:
        result["overrides_after"] = None

    # Regenerate reports/agent_list.json from the corrected DB.
    proc = subprocess.run(
        ["python3", os.path.join(BASE, "build_deposit_report.py")],
        capture_output=True, text=True,
    )
    result["build_deposit_report_returncode"] = proc.returncode
    result["build_deposit_report_stdout_tail"] = proc.stdout[-3000:]
    result["build_deposit_report_stderr_tail"] = proc.stderr[-3000:]
    proc.check_returncode()

    result["status"] = "success"


def main():
    result = {}
    try:
        run_migration(result)
    except Exception:
        result["status"] = "error"
        result["traceback"] = traceback.format_exc()
        print(result["traceback"])

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "fix_dupe_agent_names.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/fix_dupe_agent_names.json"], check=True)
    commit = subprocess.run(["git", "commit", "-m", "debug: dupe agent name merge result"])
    if commit.returncode == 0:
        subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2, default=str))

    if result.get("status") != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
