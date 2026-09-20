"""One-off read-only diagnostic: check master_userlist.db's users table
count right now, after the first of two separate userlist-upload ingest
runs (file 1 of 2) completed, to see whether that single-file run already
triggered another prune (deleting anyone not in file 1) before the second
run was cancelled. Writes results to debug/post_upload_state.json and
commits it back to the repo. One-off; delete both this script and its
workflow after use.
"""
import json
import os
import sqlite3
import subprocess

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
    result = {
        "users_count": cur.execute("SELECT COUNT(*) FROM users").fetchone()[0],
    }
    try:
        result["removed_users_count"] = cur.execute("SELECT COUNT(*) FROM removed_users").fetchone()[0]
    except Exception as e:
        result["removed_users_error"] = f"{type(e).__name__}: {e}"
    conn.close()

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "post_upload_state.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/post_upload_state.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: post-upload user count check"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
