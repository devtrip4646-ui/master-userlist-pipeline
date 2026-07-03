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

master_userlist.db (VIP level, total deposit, new user_ids) is also kept
current on every pull via sync_master_userlist() -- see its docstring.
"""
import datetime
import json
import os
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict

import openpyxl
import requests

import ci_ingest
import ingest_update as iu

API_BASE = "https://api.dlmanagers.online/prod-api/business"
PACKAGE_ID = "5"
IST_OFFSET = datetime.timedelta(hours=5, minutes=30)
TOKEN_KEY = "config/business_api_token.txt"
TOKEN_STATUS_KEY = "config/token_status.json"
WALLET_STATE_KEY = "reports/wallet_fetch_state.json"

# Cumulative deposit ("experience") required to reach each VIP level, per the
# platform's own VIP table. VIP level is purely a function of total deposit --
# never withdrawal history. Kept in sync with build_deposit_report.py's copy.
VIP_THRESHOLDS = {
    0: 0, 1: 200, 2: 1500, 3: 9600, 4: 19600, 5: 95600, 6: 295600, 7: 795600,
    8: 1795600, 9: 3795600, 10: 8795600, 11: 16795600, 12: 28795600,
    13: 44795600, 14: 69795600, 15: 119795600,
}


def vip_level_for_total(total_recharge):
    total_recharge = total_recharge or 0.0
    level = 0
    for lvl, threshold in VIP_THRESHOLDS.items():
        if total_recharge >= threshold:
            level = max(level, lvl)
    return level


def put_token_status(s3, bucket, ok, message=None):
    s3.put_object(
        Bucket=bucket, Key=TOKEN_STATUS_KEY,
        Body=json.dumps({
            "ok": ok,
            "message": message,
            "checked_at": datetime.datetime.utcnow().isoformat() + "Z",
        }).encode("utf-8"),
        ContentType="application/json",
    )


def ist_today():
    return (datetime.datetime.utcnow() + IST_OFFSET).date()


def fetch_token(s3, bucket):
    try:
        obj = s3.get_object(Bucket=bucket, Key=TOKEN_KEY)
        token = obj["Body"].read().decode("utf-8").strip()
    except Exception as e:
        put_token_status(s3, bucket, ok=False, message="update new bearer token to run the pipeline")
        print(f"FATAL: could not load business API token from r2://{bucket}/{TOKEN_KEY}: {e}", file=sys.stderr)
        print("Set it via the 'Business API Token' form on the upload page first.", file=sys.stderr)
        sys.exit(1)
    if not token:
        put_token_status(s3, bucket, ok=False, message="update new bearer token to run the pipeline")
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


def extract_deposit_user_info(deposit_path):
    """user_id -> {phone, channel, register_time, city, create_time} from a
    water/export xlsx (column order: ... userPhone[14], channel[15], ...,
    userRegisterTime[17], ..., RegisterCity[23], ..., createTime[32], ...)."""
    wb = openpyxl.load_workbook(deposit_path, read_only=True)
    ws = wb.active
    info = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        user_id = row[3]
        if user_id is None:
            continue
        info[int(user_id)] = {
            "phone": row[14],
            "channel": row[15],
            "register_time": row[17],
            "city": row[23],
            "create_time": row[32],
        }
    wb.close()
    return info


def sync_master_userlist(master_db_path, deposit_rows, deposit_info, today):
    """VIP level is purely a function of cumulative total deposit (the platform's
    own VIP table -- level N requires total_recharge >= VIP_THRESHOLDS[N]),
    never withdrawal history. Keeps master_userlist.db current on every pull:

      1. Recomputes vip_level for EVERY existing user from their stored
         total_recharge, correcting any previously-wrong value.
      2. Adds newly-seen COMPLETE deposits to each user's total_recharge. A
         dedicated deposit_sync_time column (not the real update_time field,
         to avoid conflicting with genuine userlist re-uploads) tracks how far
         we've already counted, so re-fetching the same 5-day window on every
         run never double-counts a deposit.
      3. Inserts a minimal row (with total_recharge/vip_level computed from
         their deposits seen so far, plus phone/city/channel from deposit_info)
         for any user_id not already in the table.

    Also detects "reactivation candidates": existing users who deposited
    TODAY, using their last_active_time as it stood BEFORE this run updates
    it. This is the only place that can compute this reliably -- daily_records
    .db's deposits table is purged to a rolling 33-day window, so trying to
    derive "how long were they inactive" from deposit history alone (as the
    report originally did) silently drops every comeback after a gap longer
    than that, which is most of the 10-180/15-240 day range the Reactivation
    report needs to cover.

    Always returns (True, reactivation_candidates): the recompute pass in
    step 1 touches every existing user's vip_level every run, so
    master_userlist.db always changes."""
    conn = sqlite3.connect(master_db_path)
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE users ADD COLUMN deposit_sync_time TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists from a previous run

    existing_rows = cur.execute(
        "SELECT user_id, total_recharge, deposit_sync_time, last_active_time FROM users"
    ).fetchall()
    existing = {
        uid: {"total_recharge": tr, "sync_time": st, "last_active_time": lat}
        for uid, tr, st, lat in existing_rows
    }

    fixed = 0
    for uid, info in existing.items():
        cur.execute("UPDATE users SET vip_level = ? WHERE user_id = ?", (vip_level_for_total(info["total_recharge"]), uid))
        fixed += 1
    conn.commit()

    today_str = today.isoformat()
    today_amount = defaultdict(float)
    deltas = defaultdict(lambda: {"amount": 0.0, "max_create_time": None})
    for pay_channel, order_amount, create_time, update_time_col, status, user_id, is_first_deposit in deposit_rows:
        if status != "COMPLETE" or user_id is None or not create_time:
            continue
        if str(create_time).startswith(today_str):
            today_amount[user_id] += order_amount or 0.0
        baseline = existing.get(user_id, {}).get("sync_time")
        if baseline and str(create_time) <= str(baseline):
            continue
        d = deltas[user_id]
        d["amount"] += order_amount or 0.0
        if not d["max_create_time"] or str(create_time) > str(d["max_create_time"]):
            d["max_create_time"] = create_time

    reactivation_candidates = []
    for user_id, amount in today_amount.items():
        prior = existing.get(user_id)
        if not prior or not prior["last_active_time"]:
            continue  # brand-new / never-active user, not a "reactivation"
        try:
            prior_dt = datetime.datetime.fromisoformat(str(prior["last_active_time"]).replace(" ", "T"))
        except ValueError:
            continue
        gap_days = (today - prior_dt.date()).days
        if gap_days <= 0:
            continue  # already active as of today/yesterday going into this run
        reactivation_candidates.append({
            "user_id": user_id,
            "inactive_days": gap_days,
            "total_deposit": round(amount, 2),
        })

    new_users = updated = 0
    for user_id, d in deltas.items():
        sync_time = str(d["max_create_time"])
        if user_id not in existing:
            total = round(d["amount"], 2)
            vip = vip_level_for_total(total)
            dep = deposit_info.get(user_id, {})
            cur.execute(
                "INSERT INTO users (user_id, phone, city, channel, total_recharge, vip_level, "
                "last_active_time, deposit_sync_time, create_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, dep.get("phone"), dep.get("city"), dep.get("channel"), total, vip,
                 sync_time, sync_time, str(dep.get("register_time") or sync_time)),
            )
            new_users += 1
        else:
            new_total = round((existing[user_id]["total_recharge"] or 0.0) + d["amount"], 2)
            cur.execute(
                "UPDATE users SET total_recharge = ?, vip_level = ?, deposit_sync_time = ?, last_active_time = ? "
                "WHERE user_id = ?",
                (new_total, vip_level_for_total(new_total), sync_time, sync_time, user_id),
            )
            updated += 1

    conn.commit()
    conn.close()
    print(f"Master userlist VIP recompute: {fixed} users' vip_level recalculated from total_recharge")
    print(f"Master userlist sync: {new_users} new users inserted, {updated} users' total_recharge/vip_level updated from new deposits")
    print(f"Reactivation candidates today: {len(reactivation_candidates)}")
    return True, reactivation_candidates


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

    try:
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
    except Exception as e:
        # Every export uses the same bearer token, so any unrecoverable fetch failure
        # here is treated as an expired/invalid token -- surfaced on the upload page.
        put_token_status(s3, bucket, ok=False, message="update new bearer token to run the pipeline")
        print(f"FATAL: business API fetch failed, marking token as invalid: {e}", file=sys.stderr)
        sys.exit(1)

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

    # Keep master_userlist.db current on every pull: VIP level is derived purely
    # from cumulative total deposit (see sync_master_userlist docstring). Read
    # deposit_rows from the just-ingested daily_records.db (not the raw xlsx) so
    # this always matches what's actually stored. Always re-uploads
    # master_userlist.db (224MB) -- the vip_level recompute pass touches every
    # existing user every run.
    master_db_path = os.path.join(ci_ingest.BASE, "master_userlist.db")
    daily_db_path = os.path.join(ci_ingest.BASE, "daily_records.db")
    daily_conn = sqlite3.connect(daily_db_path)
    deposit_rows_for_sync = daily_conn.execute(
        "SELECT pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit FROM deposits"
    ).fetchall()
    daily_conn.close()
    dep_info = extract_deposit_user_info(deposit_path)
    ok, reactivation_candidates = sync_master_userlist(master_db_path, deposit_rows_for_sync, dep_info, today)
    if ok:
        subprocess.run(
            [sys.executable, os.path.join(ci_ingest.BASE, "upload_to_r2.py"), "--files", "master_userlist.db"],
            check=True,
        )
        print("Uploaded refreshed master_userlist.db to R2")

    # Handed off to build_deposit_report.py (runs next, same job/workspace) via a
    # local file rather than R2 -- this list only reflects "as of this exact run",
    # not something that needs to persist or be re-fetched independently.
    reactivation_path = os.path.join(ci_ingest.BASE, "reactivation_candidates.json")
    with open(reactivation_path, "w") as f:
        json.dump(reactivation_candidates, f)
    print(f"Wrote {len(reactivation_candidates)} reactivation candidates to {reactivation_path}")

    # Only mark the wallet target date as covered after a successful ingest
    put_wallet_state(s3, bucket, {"last_run_date": today.isoformat(), "last_wallet_target": wallet_target.isoformat()})
    print(f"Wallet state updated: last_run_date={today}")

    # Successful pull+ingest confirms the token is valid -- clear any stale alert
    put_token_status(s3, bucket, ok=True)


if __name__ == "__main__":
    main()
