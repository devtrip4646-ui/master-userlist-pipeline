"""One-off read-only diagnostic: call all THREE business-API endpoints
api_pull_ingest.py's main() hits in sequence (water/export, withdraw/export,
detail/export), in the same order, with the current saved token -- to
isolate whether ALL of them fail or just one, since a prior isolated test
of water/export alone succeeded moments before a real pipeline run still
failed end-to-end. Writes results to debug/business_api_all_endpoints.json
and commits it back to the repo. One-off; delete both this script and its
workflow after use.
"""
import datetime
import json
import os
import subprocess
import time

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


def call(token, path, payload):
    try:
        resp = requests.post(
            f"{API_BASE}/{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=payload,
            timeout=180,
        )
        ctype = resp.headers.get("content-type", "")
        is_spreadsheet = "spreadsheet" in ctype or "ms-excel" in ctype
        return {
            "http_status": resp.status_code,
            "content_type": ctype,
            "is_spreadsheet": is_spreadsheet,
            "body_first_300_chars_if_not_spreadsheet": None if is_spreadsheet else resp.text[:300],
        }
    except requests.exceptions.RequestException as e:
        return {"request_exception": f"{type(e).__name__}: {e}"}


def main():
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()

    result = {"checked_at": datetime.datetime.utcnow().isoformat()}

    obj = s3.get_object(Bucket=bucket, Key=TOKEN_KEY)
    token = obj["Body"].read().decode("utf-8").strip()
    result["token_length"] = len(token)
    result["token_last_modified"] = str(obj.get("LastModified"))

    today = datetime.datetime.utcnow().date()

    # 1. Deposits (water/export) -- same as api_pull_ingest.py
    dep_start = today - datetime.timedelta(days=4)
    result["1_water_export"] = call(token, "water/export", {
        "packageId": PACKAGE_ID, "pageNum": 1, "pageSize": 10, "useUpiQuery": "true",
        "queryDate[0]": dep_start.isoformat(), "queryDate[1]": today.isoformat(),
    })
    time.sleep(2)

    # 2. Withdrawals (withdraw/export) -- same as api_pull_ingest.py
    wd_start = today - datetime.timedelta(days=4)
    wd_end = today + datetime.timedelta(days=1)
    result["2_withdraw_export"] = call(token, "withdraw/export", {
        "packageId": PACKAGE_ID, "pageNum": 1, "pageSize": 10,
        "statusList[0]": 0, "statusList[1]": 1, "statusList[2]": 2, "statusList[3]": 3, "statusList[4]": 4,
        "queryDate[0]": f"{wd_start.isoformat()} 00:00:00", "queryDate[1]": f"{wd_end.isoformat()} 00:00:00",
    })
    time.sleep(2)

    # 3. Wallet detail (detail/export) -- same as api_pull_ingest.py
    result["3_detail_export"] = call(token, "detail/export", {
        "packageId": PACKAGE_ID, "pageNum": 1, "pageSize": 10,
        "queryDate[0]": today.isoformat(), "queryDate[1]": today.isoformat(),
    })

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "business_api_all_endpoints.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/business_api_all_endpoints.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: all-endpoints business API diagnostic"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
