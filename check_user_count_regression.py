"""One-off read-only diagnostic: the User Category & Status report on the
live dashboard shows only ~3,700 total users when there should be
375,000+. That report's data comes from `mconn` (report_master_db_path),
which is EITHER master_userlist.db directly, OR a filtered COPY with
banned users stripped out (created only when banned users exist -- see
build_deposit_report.py's main()). This checks: (1) the raw row count in
master_userlist.db's users table, (2) how many banned user ids
ban_utils.get_banned_user_ids() currently returns, to see whether the
banned-filter path is somehow excluding almost everyone instead of just
the banned ones. Writes results to debug/user_count_regression.json and
commits it back to the repo. One-off; delete both this script and its
workflow after use.
"""
import json
import os
import sqlite3
import subprocess

import boto3

import ban_utils

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

    result = {}

    head = s3.head_object(Bucket=bucket, Key="master_userlist.db")
    result["master_userlist_db_bytes"] = head["ContentLength"]
    result["master_userlist_db_mb"] = round(head["ContentLength"] / (1024 * 1024), 2)
    result["master_userlist_db_last_modified"] = str(head["LastModified"])

    conn = sqlite3.connect(MASTER_DB)
    cur = conn.cursor()
    result["raw_users_table_count"] = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    result["users_with_nonnull_create_time"] = cur.execute(
        "SELECT COUNT(*) FROM users WHERE create_time IS NOT NULL"
    ).fetchone()[0]
    result["sample_rows"] = cur.execute(
        "SELECT user_id, vip_level, total_recharge, recharge_count, last_active_time, create_time FROM users LIMIT 5"
    ).fetchall()
    result["max_user_id"] = cur.execute("SELECT MAX(user_id) FROM users").fetchone()[0]
    result["min_user_id"] = cur.execute("SELECT MIN(user_id) FROM users").fetchone()[0]
    try:
        result["ingested_files_count"] = cur.execute("SELECT COUNT(*) FROM ingested_files").fetchone()[0]
        result["recent_ingested_files"] = cur.execute(
            "SELECT filename, ingested_at FROM ingested_files ORDER BY ingested_at DESC LIMIT 15"
        ).fetchall()
    except Exception as e:
        result["ingested_files_error"] = f"{type(e).__name__}: {e}"
    result["all_tables"] = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()

    try:
        banned_ids = ban_utils.get_banned_user_ids(MASTER_DB)
        result["banned_user_count"] = len(banned_ids)
    except Exception as e:
        result["banned_user_count_error"] = f"{type(e).__name__}: {e}"

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "user_count_regression.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/user_count_regression.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: user count regression check"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
