"""One-off read-only diagnostic: check whether today's (Sep 20) manually
credited New Users Lossback / Weekly Loss Bonus wallet_transactions rows
have actually been fetched into daily_records.db yet, and re-confirm
wallet_fetch_state -- since wallet_target is stuck retrying Sep 19 (524
timeout), the automatic hourly pipeline may never actually be advancing
to fetch Sep 20's wallet data at all right now. Writes results to
debug/todays_bonus_data.json and commits it back to the repo. One-off;
delete both this script and its workflow after use.
"""
import json
import os
import sqlite3
import subprocess

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


def main():
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()

    result = {}
    try:
        obj = s3.get_object(Bucket=bucket, Key=WALLET_STATE_KEY)
        result["wallet_state"] = json.loads(obj["Body"].read())
    except Exception as e:
        result["wallet_state_error"] = f"{type(e).__name__}: {e}"

    s3.download_file(bucket, "daily_records.db", DAILY_DB)
    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()

    for d in ["2026-09-19", "2026-09-20"]:
        result[f"wallet_transactions_{d}"] = cur.execute(
            "SELECT COUNT(*) FROM wallet_transactions WHERE substr(create_time,1,10) = ?", (d,)
        ).fetchone()[0]

    result["max_wallet_create_time"] = cur.execute(
        "SELECT MAX(create_time) FROM wallet_transactions"
    ).fetchone()[0]

    for gname in ["04Siya Import Excel Add", "Elle Import Excel Add"]:
        rows = cur.execute(
            "SELECT source_id, create_time FROM wallet_transactions "
            "WHERE game_name = ? ORDER BY create_time DESC LIMIT 10",
            (gname,),
        ).fetchall()
        result[f"recent_{gname}"] = rows

    try:
        result["bonuses_today_by_category"] = cur.execute(
            "SELECT matched_category, COUNT(*), SUM(change_value) FROM bonuses "
            "WHERE substr(create_time,1,10) = '2026-09-20' GROUP BY matched_category ORDER BY 2 DESC"
        ).fetchall()
    except Exception as e:
        result["bonuses_error"] = f"{type(e).__name__}: {e}"

    conn.close()

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "todays_bonus_data.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/todays_bonus_data.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: today's bonus data check"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
