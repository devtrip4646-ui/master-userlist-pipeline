"""One-off read-only diagnostic: reproduce the exact business-API call
api_pull_ingest.py makes (same endpoint, same payload, current saved
token) and capture the REAL underlying error -- status code, response
body, exception type -- instead of the generic "invalid token" message
every exception gets collapsed into by main()'s blanket except-clause.
Writes results to debug/business_api_error.json and commits it back to
the repo. One-off; delete both this script and its workflow after use.
"""
import datetime
import json
import os
import subprocess

import boto3
import requests

API_BASE = "https://api.dlmanagers.online/prod-api/business"
PACKAGE_ID = "5"
TOKEN_KEY = "config/business_api_token.txt"
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

    result = {"checked_at": datetime.datetime.utcnow().isoformat()}

    try:
        obj = s3.get_object(Bucket=bucket, Key=TOKEN_KEY)
        token = obj["Body"].read().decode("utf-8").strip()
        result["token_length"] = len(token)
        result["token_last_modified"] = str(obj.get("LastModified"))
    except Exception as e:
        result["token_read_error"] = f"{type(e).__name__}: {e}"
        token = None

    if token:
        today = datetime.datetime.utcnow().date()
        dep_start = today - datetime.timedelta(days=4)
        try:
            resp = requests.post(
                f"{API_BASE}/water/export",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "packageId": PACKAGE_ID, "pageNum": 1, "pageSize": 10, "useUpiQuery": "true",
                    "queryDate[0]": dep_start.isoformat(), "queryDate[1]": today.isoformat(),
                },
                timeout=60,
            )
            result["http_status"] = resp.status_code
            result["response_headers_content_type"] = resp.headers.get("content-type")
            result["response_body_first_1000_chars"] = resp.text[:1000]
        except requests.exceptions.RequestException as e:
            result["request_exception"] = f"{type(e).__name__}: {e}"

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "business_api_error.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/business_api_error.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: business API call diagnostic"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
