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


def sync_master_userlist(master_db_path, deposit_rows, withdrawal_activity, wallet_activity, deposit_info, today):
    """VIP level and total_recharge are purely a function of cumulative
    deposits (the platform's own VIP table -- level N requires
    total_recharge >= VIP_THRESHOLDS[N]), never withdrawal or wallet
    activity. But last_active_time -- "has this user touched the platform at
    all" -- is bumped by ANY of deposit, withdrawal, or wallet (bet)
    activity, whichever is most recent. Keeps master_userlist.db current on
    every pull:

      1. Recomputes vip_level for every existing user from their stored
         total_recharge, correcting any previously-wrong value -- but only
         WRITES when it actually changed.
      2. Adds newly-seen COMPLETE deposits to each user's total_recharge. A
         dedicated deposit_sync_time column (not the real update_time field,
         to avoid conflicting with genuine userlist re-uploads) tracks how far
         we've already counted, so re-fetching the same 5-day window on every
         run never double-counts a deposit.
      3. Bumps last_active_time for any user touched by a deposit,
         withdrawal, or wallet transaction more recent than their current
         value -- again, only writes when it actually moves forward.
      4. Inserts a minimal row for any user_id seen in ANY of the three
         sources but not already in the table (phone/city/channel only
         available when the insert is deposit-sourced).

    withdrawal_activity/wallet_activity are {user_id: latest create_time str}
    -- computed once via a cheap GROUP BY MAX query in main() rather than
    scanned row-by-row here, since wallet_transactions alone can be tens of
    millions of rows across its 33-day window.

    Skipping no-op writes (instead of touching every row every run
    unconditionally) is what keeps this run's SQLite write volume, and
    therefore its runtime/GitHub Actions billed minutes, proportional to
    what actually changed rather than to the full user table every time.

    Also detects "reactivation candidates": existing users active TODAY
    (via any of the three sources), using their last_active_time as it stood
    BEFORE this run updates it. This is the only place that can compute this
    reliably -- daily_records.db's deposits/withdrawals/wallet tables are
    purged to a rolling 33-day window, so trying to derive "how long were
    they inactive" from that history alone (as the report originally did)
    silently drops every comeback after a gap longer than that, which is
    most of the 10-180/15-240 day range the Reactivation report needs to
    cover.

    Also detects "VIP upgrade candidates": users who were in the near-upgrade
    cohort (gap Rs 1-1000 for VIP2-4, Rs 1-50000 for VIP5-15) as of the START
    of today and have since crossed into the next tier. This can't just
    compare "before this run" vs "after this run" -- the pipeline runs
    hourly, so a user could cross a tier in one run and cross again in a
    later run the same day, and each run's report is freshly regenerated
    (not cumulative), so a naive per-run diff would silently lose earlier
    upgrades from earlier today. Instead, a (vip_level, total_recharge)
    snapshot is taken once, on the first run of each calendar day (into the
    vip_day_start table, before any of today's updates are applied), and
    every run for the rest of the day compares current state against that
    same stable snapshot.

    Returns (changed, reactivation_candidates, vip_upgrade_candidates) --
    changed is True iff at least one row was actually inserted or updated
    this run. vip_upgrade_candidates is {"low": [...], "high": [...]}."""
    conn = sqlite3.connect(master_db_path)
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE users ADD COLUMN deposit_sync_time TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists from a previous run

    cur.execute(
        "CREATE TABLE IF NOT EXISTS vip_day_start "
        "(user_id INTEGER PRIMARY KEY, vip_level INTEGER, total_recharge REAL)"
    )
    cur.execute("CREATE TABLE IF NOT EXISTS vip_day_start_meta (snapshot_date TEXT)")
    today_str = today.isoformat()
    meta_row = cur.execute("SELECT snapshot_date FROM vip_day_start_meta").fetchone()
    snapshot_created = not meta_row or meta_row[0] != today_str
    if snapshot_created:
        # New day (or first run ever) -- snapshot BEFORE any of today's
        # updates are applied below, so it reflects yesterday's end-of-day
        # state and stays stable across every run for the rest of today.
        # Must force a reupload below even if nothing else changes this run
        # (see `changed` at the bottom) -- otherwise this snapshot never
        # reaches R2, and the next run would re-snapshot from ITS
        # already-partway-through-the-day state instead of true day-start.
        cur.execute("DELETE FROM vip_day_start")
        cur.execute(
            "INSERT INTO vip_day_start (user_id, vip_level, total_recharge) "
            "SELECT user_id, vip_level, total_recharge FROM users"
        )
        cur.execute("DELETE FROM vip_day_start_meta")
        cur.execute("INSERT INTO vip_day_start_meta (snapshot_date) VALUES (?)", (today_str,))
        conn.commit()

    existing_rows = cur.execute(
        "SELECT user_id, total_recharge, vip_level, deposit_sync_time, last_active_time FROM users"
    ).fetchall()
    existing = {
        uid: {"total_recharge": tr, "vip_level": vl, "sync_time": st, "last_active_time": lat}
        for uid, tr, vl, st, lat in existing_rows
    }

    fixed = 0
    for uid, info in existing.items():
        correct_vip = vip_level_for_total(info["total_recharge"])
        if correct_vip != info["vip_level"]:
            cur.execute("UPDATE users SET vip_level = ? WHERE user_id = ?", (correct_vip, uid))
            info["vip_level"] = correct_vip
            fixed += 1
    conn.commit()

    today_amount = defaultdict(float)
    today_active = set()
    deltas = defaultdict(lambda: {"amount": 0.0, "max_create_time": None})
    for pay_channel, order_amount, create_time, update_time_col, status, user_id, is_first_deposit in deposit_rows:
        if status != "COMPLETE" or user_id is None or not create_time:
            continue
        if str(create_time).startswith(today_str):
            today_amount[user_id] += order_amount or 0.0
            today_active.add(user_id)
        baseline = existing.get(user_id, {}).get("sync_time")
        if baseline and str(create_time) <= str(baseline):
            continue
        d = deltas[user_id]
        d["amount"] += order_amount or 0.0
        if not d["max_create_time"] or str(create_time) > str(d["max_create_time"]):
            d["max_create_time"] = create_time

    for user_id, ts in withdrawal_activity.items():
        if ts and str(ts).startswith(today_str):
            today_active.add(user_id)
    for user_id, ts in wallet_activity.items():
        if ts and str(ts).startswith(today_str):
            today_active.add(user_id)

    reactivation_candidates = []
    for user_id in today_active:
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
            "total_deposit": round(today_amount.get(user_id, 0.0), 2),
        })

    # Union of every user touched by ANY of the three sources this run --
    # each may need a last_active_time bump even with zero deposit delta.
    touched_users = set(deltas.keys()) | set(withdrawal_activity.keys()) | set(wallet_activity.keys())

    new_users = updated = 0
    for user_id in touched_users:
        d = deltas.get(user_id)
        candidate_times = []
        if d and d["max_create_time"]:
            candidate_times.append(str(d["max_create_time"]))
        if withdrawal_activity.get(user_id):
            candidate_times.append(str(withdrawal_activity[user_id]))
        if wallet_activity.get(user_id):
            candidate_times.append(str(wallet_activity[user_id]))
        if not candidate_times:
            continue
        latest_activity = max(candidate_times)

        prior = existing.get(user_id)
        if prior is None:
            deposit_amount = round(d["amount"], 2) if d else 0.0
            vip = vip_level_for_total(deposit_amount)
            dep = deposit_info.get(user_id, {})
            deposit_sync_time = str(d["max_create_time"]) if d and d["max_create_time"] else None
            cur.execute(
                "INSERT INTO users (user_id, phone, city, channel, total_recharge, vip_level, "
                "last_active_time, deposit_sync_time, create_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, dep.get("phone"), dep.get("city"), dep.get("channel"), deposit_amount, vip,
                 latest_activity, deposit_sync_time, str(dep.get("register_time") or latest_activity)),
            )
            new_users += 1
        else:
            sets, params = [], []
            if d and d["max_create_time"]:
                new_total = round((prior["total_recharge"] or 0.0) + d["amount"], 2)
                new_vip = vip_level_for_total(new_total)
                sets += ["total_recharge = ?", "vip_level = ?", "deposit_sync_time = ?"]
                params += [new_total, new_vip, str(d["max_create_time"])]
                prior["total_recharge"] = new_total
                prior["vip_level"] = new_vip
            current_last_active = prior["last_active_time"]
            if not current_last_active or latest_activity > str(current_last_active):
                sets.append("last_active_time = ?")
                params.append(latest_activity)
            if sets:
                params.append(user_id)
                cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE user_id = ?", params)
                updated += 1

    # VIP upgrade candidates: compare each user's CURRENT vip_level (as of
    # right now, after everything above) against the stable day-start
    # snapshot. Only counts users who were actually in the near-upgrade
    # cohort at day start -- a user who jumped several tiers from far away
    # (a huge lump-sum deposit) doesn't belong in a "near upgrade converted"
    # report.
    day_start = {
        uid: {"vip_level": vl, "total_recharge": tr}
        for uid, vl, tr in cur.execute("SELECT user_id, vip_level, total_recharge FROM vip_day_start").fetchall()
    }
    vip_upgrade_low, vip_upgrade_high = [], []
    for user_id, ds in day_start.items():
        cur_info = existing.get(user_id)
        if not cur_info or cur_info["vip_level"] <= ds["vip_level"]:
            continue
        ds_vip = ds["vip_level"]
        ds_total = ds["total_recharge"] or 0.0
        if ds_vip >= 15 or (ds_vip + 1) not in VIP_THRESHOLDS:
            continue  # no next tier to have been "near"
        gap = VIP_THRESHOLDS[ds_vip + 1] - ds_total
        deposit_today = round(today_amount.get(user_id, 0.0), 2)
        row = {
            "user_id": user_id,
            "vip_before": ds_vip,
            "vip_after": cur_info["vip_level"],
            "total_deposit": deposit_today,
            "amount_over_minimum": round(deposit_today - gap, 2),
        }
        if 2 <= ds_vip <= 4 and 1 <= gap <= 1000:
            vip_upgrade_low.append(row)
        elif 5 <= ds_vip <= 15 and 1 <= gap <= 50000:
            vip_upgrade_high.append(row)
    vip_upgrade_candidates = {"low": vip_upgrade_low, "high": vip_upgrade_high}

    conn.commit()
    conn.close()
    print(f"Master userlist VIP recompute: {fixed} users' vip_level actually changed")
    print(f"Master userlist sync: {new_users} new users inserted, {updated} users updated from deposit/withdrawal/wallet activity")
    print(f"Reactivation candidates today: {len(reactivation_candidates)}")
    print(f"VIP upgrade candidates today: {len(vip_upgrade_low)} low, {len(vip_upgrade_high)} high")
    changed = fixed > 0 or new_users > 0 or updated > 0 or snapshot_created
    return changed, reactivation_candidates, vip_upgrade_candidates


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

    # Keep master_userlist.db current on every pull: VIP level/total_recharge
    # are derived purely from cumulative deposits, but last_active_time is
    # bumped by ANY of deposit, withdrawal, or wallet activity (see
    # sync_master_userlist docstring). Read straight from the just-ingested
    # daily_records.db (not the raw xlsx files) so this always matches what's
    # actually stored. withdrawal/wallet activity is aggregated via a single
    # GROUP BY MAX query each -- wallet_transactions alone can be tens of
    # millions of rows across its 33-day window, so fetching every row into
    # Python here would be a real cost, not just a correctness risk.
    master_db_path = os.path.join(ci_ingest.BASE, "master_userlist.db")
    daily_db_path = os.path.join(ci_ingest.BASE, "daily_records.db")
    daily_conn = sqlite3.connect(daily_db_path)
    deposit_rows_for_sync = daily_conn.execute(
        "SELECT pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit FROM deposits"
    ).fetchall()
    # idx_wd_user/idx_wt_user (created once in build_daily_records.py, already
    # persisted in R2) let SQLite group by user_id without a full sort. A new
    # composite (user_id, create_time) index isn't worth adding here: this
    # local daily_records.db copy is opened AFTER ingest_update.py already
    # re-uploaded it to R2, so a new index built here would just be rebuilt
    # from scratch on every future run instead of paying for itself once.
    withdrawal_activity = dict(daily_conn.execute(
        "SELECT user_id, MAX(create_time) FROM withdrawals WHERE user_id IS NOT NULL GROUP BY user_id"
    ).fetchall())
    wallet_activity = dict(daily_conn.execute(
        "SELECT user_id, MAX(create_time) FROM wallet_transactions WHERE user_id IS NOT NULL GROUP BY user_id"
    ).fetchall())
    daily_conn.close()
    dep_info = extract_deposit_user_info(deposit_path)
    ok, reactivation_candidates, vip_upgrade_candidates = sync_master_userlist(
        master_db_path, deposit_rows_for_sync, withdrawal_activity, wallet_activity, dep_info, today
    )
    if ok:
        subprocess.run(
            [sys.executable, os.path.join(ci_ingest.BASE, "upload_to_r2.py"), "--files", "master_userlist.db"],
            check=True,
        )
        print("Uploaded refreshed master_userlist.db to R2")

    # Handed off to build_deposit_report.py (runs next, same job/workspace) via
    # local files rather than R2 -- these only reflect "as of this exact run",
    # not something that needs to persist or be re-fetched independently.
    reactivation_path = os.path.join(ci_ingest.BASE, "reactivation_candidates.json")
    with open(reactivation_path, "w") as f:
        json.dump(reactivation_candidates, f)
    print(f"Wrote {len(reactivation_candidates)} reactivation candidates to {reactivation_path}")

    vip_upgrade_path = os.path.join(ci_ingest.BASE, "vip_upgrade_candidates.json")
    with open(vip_upgrade_path, "w") as f:
        json.dump(vip_upgrade_candidates, f)
    print(f"Wrote {len(vip_upgrade_candidates['low'])} low + {len(vip_upgrade_candidates['high'])} high VIP upgrade candidates to {vip_upgrade_path}")

    # Only mark the wallet target date as covered after a successful ingest
    put_wallet_state(s3, bucket, {"last_run_date": today.isoformat(), "last_wallet_target": wallet_target.isoformat()})
    print(f"Wallet state updated: last_run_date={today}")

    # Successful pull+ingest confirms the token is valid -- clear any stale alert
    put_token_status(s3, bucket, ok=True)


if __name__ == "__main__":
    main()
