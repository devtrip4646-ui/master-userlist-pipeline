"""One-off read-only diagnostic: fresh snapshot (as of now, Sep 21) of
wallet_fetch_state.json and wallet_transactions coverage, to see whether
the automated hourly pull has actually advanced past Sep 18/19/20 or is
still stuck, and whether today's New Users Lossback / Weekly Loss Bonus
credits are present in wallet_transactions and/or bonuses. Always writes
debug/wallet_pipeline_now.json (including a traceback on failure) and
commits it. One-off; delete this script and its workflow after use.
"""
import json
import os
import sqlite3
import subprocess
import traceback

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")
WALLET_STATE_KEY = "reports/wallet_fetch_state.json"


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def run_check(result):
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()

    try:
        obj = s3.get_object(Bucket=bucket, Key=WALLET_STATE_KEY)
        result["wallet_state"] = json.loads(obj["Body"].read())
    except Exception as e:
        result["wallet_state_error"] = f"{type(e).__name__}: {e}"

    s3.download_file(bucket, "daily_records.db", DAILY_DB)
    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()

    for d in ["2026-09-19", "2026-09-20", "2026-09-21"]:
        result[f"wallet_transactions_{d}"] = cur.execute(
            "SELECT COUNT(*) FROM wallet_transactions WHERE substr(create_time,1,10) = ?", (d,)
        ).fetchone()[0]

    result["max_wallet_create_time"] = cur.execute(
        "SELECT MAX(create_time) FROM wallet_transactions"
    ).fetchone()[0]

    for gname in ["04Siya Import Excel Add", "Elle Import Excel Add"]:
        rows = cur.execute(
            "SELECT source_id, create_time FROM wallet_transactions "
            "WHERE game_name = ? AND create_time >= '2026-09-20' "
            "ORDER BY create_time DESC LIMIT 15",
            (gname,),
        ).fetchall()
        result[f"recent_{gname}_since_sep20"] = rows

    for d in ["2026-09-20", "2026-09-21"]:
        result[f"bonuses_{d}_by_category"] = cur.execute(
            "SELECT matched_category, COUNT(*), SUM(change_value) FROM bonuses "
            "WHERE substr(create_time,1,10) = ? GROUP BY matched_category ORDER BY 2 DESC",
            (d,),
        ).fetchall()

    conn.close()
    result["status"] = "success"


def main():
    result = {}
    try:
        run_check(result)
    except Exception:
        result["status"] = "error"
        result["traceback"] = traceback.format_exc()
        print(result["traceback"])

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "wallet_pipeline_now.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/wallet_pipeline_now.json"], check=True)
    commit = subprocess.run(["git", "commit", "-m", "debug: fresh wallet pipeline state check"])
    if commit.returncode == 0:
        subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2, default=str))

    if result.get("status") != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
