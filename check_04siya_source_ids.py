"""One-off read-only diagnostic: dump distinct source_id/source values for
wallet_transactions rows with game_name = '04Siya Import Excel Add', so the
New Users Lossback bonus-classification rule in ingest_update.py's
classify_bonus() can be corrected against real data (some rows are
matching the current "starts with 'new users lossback'" rule, many aren't).
Writes results to debug/04siya_source_ids.json and commits it back to the
repo (rather than just printing to Actions logs) so it can be read without
repo admin access. Deletes itself and its workflow after use, per this
repo's established diagnostic-script convention.
"""
import json
import os
import sqlite3
import subprocess

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
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
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    s3.download_file(bucket, "daily_records.db", DAILY_DB)

    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()

    groups = cur.execute(
        "SELECT source_id, source, COUNT(*), SUM(change_value) "
        "FROM wallet_transactions WHERE game_name = '04Siya Import Excel Add' "
        "GROUP BY source_id, source ORDER BY 3 DESC"
    ).fetchall()

    result = {"total_groups": len(groups), "groups": []}
    for source_id, source, count, total in groups:
        samples = cur.execute(
            "SELECT user_id, change_value, change_after, create_time FROM wallet_transactions "
            "WHERE game_name = '04Siya Import Excel Add' AND source_id IS ? AND source IS ? "
            "ORDER BY create_time DESC LIMIT 5",
            (source_id, source),
        ).fetchall()
        result["groups"].append({
            "source_id": source_id,
            "source": source,
            "count": count,
            "total_change_value": total,
            "samples": [
                {"user_id": u, "change_value": cv, "change_after": ca, "create_time": ct}
                for u, cv, ca, ct in samples
            ],
        })

    conn.close()

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "04siya_source_ids.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/04siya_source_ids.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: dump 04Siya Import Excel Add source_id groups"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(f"Wrote {len(groups)} groups to debug/04siya_source_ids.json and pushed")


if __name__ == "__main__":
    main()
