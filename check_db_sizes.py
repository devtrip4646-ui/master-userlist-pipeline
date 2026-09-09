"""One-off read-only report: current file sizes of master_userlist.db and
daily_records.db in R2, via S3 head_object (no download needed). Writes
results to debug/db_sizes.json and commits it back to the repo. One-off;
delete both this script and its workflow after use.
"""
import json
import os
import subprocess

import boto3


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
    for key in ["master_userlist.db", "daily_records.db"]:
        head = s3.head_object(Bucket=bucket, Key=key)
        result[key] = {
            "bytes": head["ContentLength"],
            "mb": round(head["ContentLength"] / (1024 * 1024), 2),
            "last_modified": str(head["LastModified"]),
        }

    base = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(base, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "db_sizes.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/db_sizes.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: db file sizes"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
