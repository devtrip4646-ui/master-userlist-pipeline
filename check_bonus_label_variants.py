"""One-off read-only diagnostic: every distinct matched_category currently in
the bonuses table (whole retained window) with claim count, distinct users,
total value and first/last date, plus a sample raw game_name/source_id per
label, so near-duplicate labels (casing/spacing/suffix variants) can be
grouped. Always writes debug/bonus_label_variants.json (including a
traceback on failure) and commits it. One-off; delete this script and its
workflow after use.
"""
import json
import os
import sqlite3
import subprocess
import time
import traceback

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


def download_with_retry(s3, bucket, key, dest, attempts=5):
    for i in range(attempts):
        try:
            s3.download_file(bucket, key, dest)
            return
        except Exception:
            if i == attempts - 1:
                raise
            time.sleep(20)


def run(result):
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    download_with_retry(s3, bucket, "daily_records.db", DAILY_DB)
    conn = sqlite3.connect(DAILY_DB)
    rows = conn.execute(
        "SELECT matched_category, COUNT(*), COUNT(DISTINCT user_id), SUM(change_value), "
        "MIN(substr(create_time,1,10)), MAX(substr(create_time,1,10)) "
        "FROM bonuses WHERE matched_category IS NOT NULL GROUP BY matched_category"
    ).fetchall()
    cats = []
    for cat, n, users, total, first, last in rows:
        sample = conn.execute(
            "SELECT w.game_name, w.source, w.source_id FROM bonuses b JOIN wallet_transactions w ON w.id = b.id "
            "WHERE b.matched_category = ? LIMIT 1", (cat,)).fetchone()
        cats.append({"category": cat, "claims": n, "users": users, "total": round(total or 0.0, 2),
                     "first": first, "last": last,
                     "sample_game_name": sample[0] if sample else None,
                     "sample_source": sample[1] if sample else None,
                     "sample_source_id": sample[2] if sample else None})
    conn.close()
    cats.sort(key=lambda c: -c["total"])
    result["categories"] = cats
    result["status"] = "success"


def main():
    result = {}
    try:
        run(result)
    except Exception:
        result["status"] = "error"
        result["traceback"] = traceback.format_exc()
        print(result["traceback"])
    os.makedirs(os.path.join(BASE, "debug"), exist_ok=True)
    with open(os.path.join(BASE, "debug", "bonus_label_variants.json"), "w") as f:
        json.dump(result, f, indent=1, default=str)
    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "-f", "debug/bonus_label_variants.json"], check=True)
    if subprocess.run(["git", "commit", "-m", "debug: bonus label variants"]).returncode == 0:
        for _ in range(5):
            if subprocess.run(["git", "push"]).returncode == 0:
                break
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        else:
            raise RuntimeError("git push failed after 5 rebase retries")
    print(f"status={result.get('status')} categories={len(result.get('categories', []))}")
    if result.get("status") != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
