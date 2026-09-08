"""One-off read-only report: distinct `city` values in the users table that
REGION_MAPPING (build_deposit_report.py) does NOT recognize, causing them to
fall into the Region vs VIP Depositor Matrix's "Unknown" bucket -- with
user counts so the most-impactful ones can be prioritized. Writes results
to debug/unmapped_regions.json and commits it back to the repo. One-off;
delete both this script and its workflow after use.
"""
import json
import os
import sqlite3
import subprocess
import sys

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")

sys.path.insert(0, BASE)
from build_deposit_report import REGION_MAPPING  # noqa: E402


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

    rows = cur.execute(
        "SELECT city, COUNT(*) FROM users GROUP BY city ORDER BY 2 DESC"
    ).fetchall()
    conn.close()

    unmapped = []
    for city, count in rows:
        key = str(city).strip().lower() if city else ""
        if key not in REGION_MAPPING:
            unmapped.append({"raw_city": city, "user_count": count})

    result = {
        "total_distinct_city_values": len(rows),
        "unmapped_count": len(unmapped),
        "unmapped_total_users": sum(u["user_count"] for u in unmapped),
        "unmapped": unmapped,
    }

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "unmapped_regions.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/unmapped_regions.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: unmapped region/city values"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
