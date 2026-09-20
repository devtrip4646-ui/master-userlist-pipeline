"""One-off read-only diagnostic: check if the R2 bucket has object
versioning enabled, which would be the only way to actually recover a
prior version of master_userlist.db from before the mass user deletion,
rather than just restoring the currently-missing rows via a fresh
userlist upload. Writes results to debug/r2_versioning.json and commits
it back to the repo. One-off; delete both this script and its workflow
after use.
"""
import json
import os
import subprocess

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))


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
        versioning = s3.get_bucket_versioning(Bucket=bucket)
        result["versioning_status"] = versioning.get("Status", "Disabled (not returned = disabled)")
    except Exception as e:
        result["versioning_check_error"] = f"{type(e).__name__}: {e}"

    try:
        versions = s3.list_object_versions(Bucket=bucket, Prefix="master_userlist.db")
        result["master_userlist_db_versions"] = [
            {"version_id": v.get("VersionId"), "last_modified": str(v.get("LastModified")), "size": v.get("Size"), "is_latest": v.get("IsLatest")}
            for v in versions.get("Versions", [])
        ]
    except Exception as e:
        result["list_versions_error"] = f"{type(e).__name__}: {e}"

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "r2_versioning.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/r2_versioning.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: R2 bucket versioning check"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
