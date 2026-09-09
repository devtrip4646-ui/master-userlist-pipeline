"""One-off read-only report: VIP level distribution now vs. the earliest
date daily_records.db's deposit history still covers (its rolling window,
not the dashboard's actual July 2 start -- that data no longer exists
anywhere). Reconstructs each user's cumulative deposit total AS OF that
earliest date by subtracting every deposit from then to now from their
current total_recharge (same technique as reconstruct_vip_upgrade_history.py),
then maps both totals to VIP levels via VIP_THRESHOLDS. Writes results to
debug/vip_level_growth.json and commits it back to the repo. One-off;
delete both this script and its workflow after use.
"""
import json
import os
import sqlite3
import subprocess

import boto3

import ban_utils

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")
DAILY_DB = os.path.join(BASE, "daily_records.db")

VIP_THRESHOLDS = {
    0: 0, 1: 200, 2: 1500, 3: 9600, 4: 19600, 5: 95600, 6: 295600, 7: 795600,
    8: 1795600, 9: 3795600, 10: 8795600, 11: 16795600, 12: 28795600,
    13: 44795600, 14: 69795600, 15: 119795600,
}
SORTED_LEVELS = sorted(VIP_THRESHOLDS)


def vip_level_for(cumulative):
    level = 0
    for lvl in SORTED_LEVELS:
        if cumulative >= VIP_THRESHOLDS[lvl]:
            level = lvl
        else:
            break
    return level


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
    s3.download_file(bucket, "daily_records.db", DAILY_DB)

    banned_ids = set(ban_utils.get_banned_user_ids(MASTER_DB))

    mconn = sqlite3.connect(MASTER_DB)
    total_recharge_by_user = {
        uid: (tr or 0.0) for uid, tr in mconn.execute("SELECT user_id, total_recharge FROM users").fetchall()
        if uid not in banned_ids
    }
    mconn.close()

    dconn = sqlite3.connect(DAILY_DB)
    earliest_row = dconn.execute(
        "SELECT MIN(create_time) FROM deposits WHERE status = 'COMPLETE' AND user_id IS NOT NULL"
    ).fetchone()
    earliest_date = str(earliest_row[0])[:10] if earliest_row and earliest_row[0] else None

    dep_since_start = {}
    if earliest_date:
        for user_id, amount in dconn.execute(
            "SELECT user_id, SUM(order_amount) FROM deposits "
            "WHERE status = 'COMPLETE' AND user_id IS NOT NULL AND create_time >= ? GROUP BY user_id",
            (earliest_date,),
        ).fetchall():
            dep_since_start[user_id] = amount or 0.0
    dconn.close()

    counts_now = {lvl: 0 for lvl in SORTED_LEVELS}
    counts_start = {lvl: 0 for lvl in SORTED_LEVELS}
    for user_id, total_now in total_recharge_by_user.items():
        level_now = vip_level_for(total_now)
        counts_now[level_now] += 1

        running_before = total_now - dep_since_start.get(user_id, 0.0)
        level_start = vip_level_for(running_before)
        counts_start[level_start] += 1

    rows = []
    for lvl in SORTED_LEVELS:
        start_n = counts_start[lvl]
        now_n = counts_now[lvl]
        increase = now_n - start_n
        pct = round(increase / start_n * 100, 2) if start_n else (None if now_n == 0 else "new")
        rows.append({
            "vip_level": lvl,
            "users_at_start": start_n,
            "users_now": now_n,
            "increase": increase,
            "increase_pct": pct,
        })

    result = {
        "earliest_reconstructable_date": earliest_date,
        "total_users_now": sum(counts_now.values()),
        "total_users_at_start": sum(counts_start.values()),
        "rows": rows,
    }

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "vip_level_growth.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/vip_level_growth.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: VIP level growth since " + str(earliest_date)], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
