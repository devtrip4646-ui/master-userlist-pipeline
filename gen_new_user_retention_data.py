"""One-off read-only data pull for the "New users retention" Sep+Oct report:
every Promotion-registered, non-test user registered 2026-09-01 through
yesterday (IST), with their channel, raw city, lifetime counters from the
users table, and the dates of their COMPLETE deposits / completed
withdrawals from daily_records.db (complete for anyone registered inside
the ~33-day window; earlier registrants have partial history). Also dumps
value distributions (register_channel, channel, city, test flag) so the
mapping to your Superset report can be verified. Always writes
debug/new_user_retention_data.json (traceback on failure) and commits it.
One-off; delete this script and its workflow after use.
"""
import json
import os
import sqlite3
import subprocess
import time
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timedelta

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")
MASTER_DB = os.path.join(BASE, "master_userlist.db")
START = "2026-09-01"


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
    download_with_retry(s3, bucket, "master_userlist.db", MASTER_DB)

    today = (datetime.utcnow() + timedelta(hours=5, minutes=30)).date().isoformat()
    result["window"] = {"start": START, "end_exclusive": today}

    m = sqlite3.connect(MASTER_DB)
    all_rows = m.execute(
        "SELECT user_id, substr(create_time,1,10), register_channel, is_test_account, channel, city, "
        "recharge_count, total_recharge, total_withdrawal, register_source FROM users "
        "WHERE substr(create_time,1,10) >= ? AND substr(create_time,1,10) < ?",
        (START, today),
    ).fetchall()
    m.close()
    result["users_registered_in_window_all_channels"] = len(all_rows)
    result["register_channel_counts"] = Counter(str(r[2]) for r in all_rows).most_common(30)
    result["is_test_account_counts"] = Counter(str(r[3]) for r in all_rows).most_common(10)

    result["register_source_counts_all"] = Counter(str(r[9]) for r in all_rows).most_common(40)
    result["registerchannel_x_channel_x_source_all"] = Counter(
        (str(r[2]), str(r[4]), str(r[9])) for r in all_rows
    ).most_common(120)

    promo = [r for r in all_rows if str(r[2]).strip().lower() == "promotion"]
    result["promotion_users_all_incl_test"] = len(promo)
    real = [r for r in promo if not r[3]]  # is_test_account NULL / 0
    result["promotion_users_non_test"] = len(real)
    result["channel_counts_promotion_non_test"] = Counter(str(r[4]) for r in real).most_common(60)
    result["source_counts_promotion_non_test"] = Counter(str(r[9]) for r in real).most_common(40)
    result["city_counts_promotion_non_test"] = Counter(str(r[5]) for r in real).most_common(250)

    ids = {r[0] for r in real}
    d = sqlite3.connect(DAILY_DB)
    dep_dates = defaultdict(list)
    for uid, day in d.execute(
        "SELECT user_id, substr(create_time,1,10) FROM deposits WHERE status = 'COMPLETE' AND user_id IS NOT NULL"
    ):
        if uid in ids:
            dep_dates[uid].append(day)
    wd_dates = defaultdict(list)
    for uid, day in d.execute(
        "SELECT user_id, substr(create_time,1,10) FROM withdrawals WHERE status = 2 AND user_id IS NOT NULL"
    ):
        if uid in ids:
            wd_dates[uid].append(day)
    result["deposit_window"] = d.execute(
        "SELECT MIN(substr(create_time,1,10)), MAX(substr(create_time,1,10)) FROM deposits"
    ).fetchone()
    d.close()

    result["users"] = [
        {
            "id": uid, "reg": reg, "ch": ch, "src": src, "city": city, "rc": rc, "tr": tr, "tw": tw,
            "dep": sorted(dep_dates.get(uid, [])), "wd": sorted(wd_dates.get(uid, [])),
        }
        for uid, reg, _regch, _test, ch, city, rc, tr, tw, src in real
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

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "new_user_retention_data.json"), "w") as f:
        json.dump(result, f, default=str, separators=(",", ":"))

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "-f", "debug/new_user_retention_data.json"], check=True)
    commit = subprocess.run(["git", "commit", "-m", "debug: new user retention data"])
    if commit.returncode == 0:
        for attempt in range(5):
            push = subprocess.run(["git", "push"])
            if push.returncode == 0:
                break
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        else:
            raise RuntimeError("git push failed after 5 rebase retries")
    print({k: v for k, v in result.items() if k not in ("users", "city_counts_promotion_non_test", "registerchannel_x_channel_x_source_all")})

    if result.get("status") != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
