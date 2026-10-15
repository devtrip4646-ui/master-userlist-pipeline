"""One-off read-only diagnostic: total size of the R2 bucket, size and object
count per top-level prefix, the 15 largest objects, and the two database
files. Always writes debug/storage_size.json (including a traceback on
failure) and commits it. One-off; delete this script and its workflow after
use.
"""
import json
import os
import subprocess
import traceback
from collections import defaultdict

import boto3


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def run(result):
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    objs = []
    token = None
    while True:
        kw = {"Bucket": bucket, "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        for o in resp.get("Contents", []):
            objs.append((o["Key"], o["Size"], o["LastModified"].isoformat()))
        if not resp.get("IsTruncated"):
            break
        token = resp["NextContinuationToken"]

    total = sum(s for _, s, _ in objs)
    by_prefix = defaultdict(lambda: [0, 0])
    for key, size, _ in objs:
        prefix = key.split("/")[0] + "/" if "/" in key else "(root)"
        by_prefix[prefix][0] += 1
        by_prefix[prefix][1] += size
    result["bucket"] = bucket
    result["object_count"] = len(objs)
    result["total_bytes"] = total
    result["total_gb"] = round(total / 1e9, 3)
    result["by_prefix"] = sorted(
        ({"prefix": p, "objects": v[0], "bytes": v[1], "mb": round(v[1] / 1e6, 1)} for p, v in by_prefix.items()),
        key=lambda r: -r["bytes"],
    )
    result["largest_objects"] = [
        {"key": k, "mb": round(s / 1e6, 1), "last_modified": lm}
        for k, s, lm in sorted(objs, key=lambda o: -o[1])[:15]
    ]
    result["databases"] = [
        {"key": k, "mb": round(s / 1e6, 1), "last_modified": lm}
        for k, s, lm in objs if k in ("daily_records.db", "master_userlist.db")
    ]
    result["status"] = "success"


def main():
    result = {}
    try:
        run(result)
    except Exception:
        result["status"] = "error"
        result["traceback"] = traceback.format_exc()
        print(result["traceback"])
    os.makedirs("debug", exist_ok=True)
    with open("debug/storage_size.json", "w") as f:
        json.dump(result, f, indent=1, default=str)
    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "-f", "debug/storage_size.json"], check=True)
    if subprocess.run(["git", "commit", "-m", "debug: storage size"]).returncode == 0:
        for _ in range(5):
            if subprocess.run(["git", "push"]).returncode == 0:
                break
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        else:
            raise RuntimeError("git push failed after 5 rebase retries")
    print(f"status={result.get('status')} total_gb={result.get('total_gb')}")
    if result.get("status") != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
