"""
Pulls deposit, withdrawal, and wallet-detail exports directly from the business
API (dlmanagers.online) and ingests them, instead of waiting for a manual file
upload. Runs on a schedule via GitHub Actions (see .github/workflows/api_pull.yml).

Deposits and withdrawals: always fetch a rolling 5-day window (today - 4 days
through today, IST) since an order created days ago can still complete, fail,
or get rejected later. ingest_update.ingest_deposits/ingest_withdrawals now use
INSERT OR REPLACE, so re-fetching the same order id with an updated status
overwrites the stale row instead of being ignored.

Wallet details: single-day export. Uses `today` (IST) on every run, except the
first run after the IST calendar date has rolled over, which uses `yesterday`
once (to finalize the previous day's data) before switching to `today` for the
rest of that day. Which date was last covered is persisted in R2 at
reports/wallet_fetch_state.json so this survives across independent runs.

The API bearer token is not a GitHub secret -- it's stored in R2 at
config/business_api_token.txt and can be updated any time via the "Business
API Token" form on the upload page, without touching GitHub settings.
"""
import datetime
import json
import os
import sys
import time

import requests

import ci_ingest
import ingest_update as iu

API_BASE = "https://api.dlmanagers.online/prod-api/business"
PACKAGE_ID = "5"
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)
TOKEN_KEY = "config/business_api_token.txt"
WALLET_STATE_KEY = "reports/wallet_fetch_state.json"


def ist_today():
    return (datetime.datetime.utcnow() + IST_OFFSET).date()


def fetch_token(s3, bucket):
    try:
        obj = s3.get_object(Bucket=bucket, Key=TOKEN_KEY)
        token = obj["Body"].read().decode("utf-8").strip()
    except Exception as e:
        print(f"FATAL: could not load business API token from r2://{bucket}/{TOKEN_KEY}: {e}", file=sys.stderr)
        print("Set it via the 'Business API Token' form on the upload page first.", file=sys.stderr)
        sys.exit(1)
    if not token:
        print(f"FATAL: business API token at r2://{bucket}/{TOKEN_KEY} is empty", file=sys.stderr)
        sys.exit(1)
    return token


def fetch_export(token, path, payload, attempts=3):
    last_err = None
    for attempt in range(1, attempts + 1):
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
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "spreadsheet" not in ctype and "ms-excel" not in ctype:
                raise RuntimeError(f"Unexpected response from {path} (content-type={ctype}): {resp.text[:300]}")
            return resp.content
        except Exception as e:
            last_err = e
            print(f"  fetch attempt {attempt}/{attempts} for {path} failed: {e}")
            if attempt < attempts:
                time.sleep(10 * attempt)
    raise last_err


def save_xlsx(content, name):
    path = os.path.join(ci_ingest.BASE, name)
    with open(path, "wb") as f:
        f.write(content)
    return path


def get_wallet_state(s3, bucket):
    try:
        obj = s3.get_object(Bucket=bucket, Key=WALLET_STATE_KEY)
        return json.loads(obj["Body"].read())
    except Exception:
        return {}


def put_wallet_state(s3, bucket, state):
    s3.put_object(Bucket=bucket, Key=WALLET_STATE_KEY, Body=json.dumps(state).encode("utf-8"),
                   ContentType="application/json")


def main():
    bucket = os.environ["R2_BUCKET"]
    s3 = ci_ingest.r2_client()

    for fname in ["master_userlist.db", "daily_records.db"]:
        local_path = os.path.join(ci_ingest.BASE, fname)
        try:
            ci_ingest.download_with_retry(s3, bucket, fname, local_path)
            print(f"Downloaded existing {fname} from R2")
        except Exception as e:
            print(f"FATAL: could not download {fname} from R2: {e}", file=sys.stderr)
            sys.exit(1)

    token = fetch_token(s3, bucket)
    today = ist_today()
    ts = int(time.time() * 1000)

    # Deposits: 5-day window, date-only bounds (confirmed inclusive of the full end day)
    dep_start = today - datetime.timedelta(days=4)
    deposit_bytes = fetch_export(token, "water/export", {
        "packageId": PACKAGE_ID, "pageNum": 1, "pageSize": 10, "useUpiQuery": "true",
        "queryDate[0]": dep_start.isoformat(), "queryDate[1]": today.isoformat(),
    })
    deposit_path = save_xlsx(deposit_bytes, f"{ts}_water_api_pull.xlsx")
    print(f"Fetched deposits {dep_start} .. {today}: {len(deposit_bytes)} bytes")

    # Withdrawals: end bound is exclusive of the named day, so use (today + 1) at
    # 00:00:00 to include all of today. Query all 5 statuses (In-Review, Processing,
    # Complete, Rejected, Failed) -- the whole point of the 5-day window is to catch
    # orders that transition into any of those terminal states after creation.
    wd_start = today - datetime.timedelta(days=4)
    wd_end = today + datetime.timedelta(days=1)
    withdraw_bytes = fetch_export(token, "withdraw/export", {
        "packageId": PACKAGE_ID, "pageNum": 1, "pageSize": 10,
        "statusList[0]": 0, "statusList[1]": 1, "statusList[2]": 2, "statusList[3]": 3, "statusList[4]": 4,
        "queryDate[0]": f"{wd_start.isoformat()} 00:00:00", "queryDate[1]": f"{wd_end.isoformat()} 00:00:00",
    })
    withdraw_path = save_xlsx(withdraw_bytes, f"{ts}_withdraw_api_pull.xlsx")
    print(f"Fetched withdrawals {wd_start} .. {today} (inclusive): {len(withdraw_bytes)} bytes")

    # Wallet: single day, with day-rollover-aware target date
    wallet_state = get_wallet_state(s3, bucket)
    last_run_date = wallet_state.get("last_run_date")
    if last_run_date != today.isoformat():
        wallet_target = today - datetime.timedelta(days=1)
        print(f"First run of {today} -- wallet export will finalize {wallet_target}")
    else:
        wallet_target = today
        print(f"Same-day rerun -- wallet export continues with {wallet_target}")
    wallet_bytes = fetch_export(token, "detail/export", {
        "packageId": PACKAGE_ID, "pageNum": 1, "pageSize": 10,
        "queryDate[0]": wallet_target.isoformat(), "queryDate[1]": wallet_target.isoformat(),
    })
    wallet_path = save_xlsx(wallet_bytes, f"{ts}_detail_api_pull.xlsx")
    print(f"Fetched wallet {wallet_target}: {len(wallet_bytes)} bytes")

    # Ingest everything in one pass (handles purge + re-upload to R2 internally)
    argv_backup = sys.argv
    sys.argv = [
        "ingest_update.py",
        "--deposits", deposit_path,
        "--withdrawals", withdraw_path,
        "--wallet", wallet_path,
    ]
    try:
        iu.main()
    finally:
        sys.argv = argv_backup

    # Only mark the wallet target date as covered after a successful ingest
    put_wallet_state(s3, bucket, {"last_run_date": today.isoformat(), "last_wallet_target": wallet_target.isoformat()})
    print(f"Wallet state updated: last_run_date={today}")


if __name__ == "__main__":
    main()
