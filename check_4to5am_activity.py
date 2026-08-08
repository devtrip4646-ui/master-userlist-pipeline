"""One-off read-only check: user asks what happened 4-5 AM IST today --
specifically whether bonuses were credited and why so many users' wallets
"got activated" in that window. First establishes whether create_time is
stored as IST-labeled or UTC-labeled strings (by comparing MAX(create_time)
against the actual current wall-clock in both zones), then reports bonus
and wallet activity for the window under whichever interpretation fits.
"""
import os
import sqlite3
from datetime import datetime, timedelta
from collections import Counter

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")


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
    s3.download_file(bucket, "daily_records.db", DAILY_DB)

    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()

    now_utc = datetime.utcnow()
    now_ist = now_utc + timedelta(hours=5, minutes=30)
    print(f"=== now UTC: {now_utc.isoformat()}  now IST: {now_ist.isoformat()} ===")

    print("=== MAX(create_time) in wallet_transactions / bonuses (to determine stored timezone) ===")
    print(" wallet_transactions MAX:", cur.execute("SELECT MAX(create_time) FROM wallet_transactions").fetchone()[0])
    print(" bonuses MAX:", cur.execute("SELECT MAX(create_time) FROM bonuses").fetchone()[0])

    # Try both interpretations of "4-5 AM IST today"
    today_ist = now_ist.date().isoformat()
    win_ist_start = f"{today_ist} 04:00:00"
    win_ist_end = f"{today_ist} 05:00:00"

    today_utc = now_utc.date().isoformat()
    yest_utc = (now_utc.date() - timedelta(days=1)).isoformat()
    win_utc_start = f"{yest_utc} 22:30:00"
    win_utc_end = f"{yest_utc} 23:30:00"

    for label, start, end in [
        ("IF create_time stored AS IST-labeled strings", win_ist_start, win_ist_end),
        ("IF create_time stored AS UTC-labeled strings (4-5AM IST = prior-day 22:30-23:30 UTC)", win_utc_start, win_utc_end),
    ]:
        print(f"\n=== {label}: window {start} .. {end} ===")
        wt_count = cur.execute(
            "SELECT COUNT(*) FROM wallet_transactions WHERE create_time >= ? AND create_time < ?", (start, end)
        ).fetchone()[0]
        wt_users = cur.execute(
            "SELECT COUNT(DISTINCT user_id) FROM wallet_transactions WHERE create_time >= ? AND create_time < ?", (start, end)
        ).fetchone()[0]
        bonus_count = cur.execute(
            "SELECT COUNT(*) FROM bonuses WHERE create_time >= ? AND create_time < ?", (start, end)
        ).fetchone()[0]
        bonus_users = cur.execute(
            "SELECT COUNT(DISTINCT user_id) FROM bonuses WHERE create_time >= ? AND create_time < ?", (start, end)
        ).fetchone()[0]
        bonus_amt = cur.execute(
            "SELECT COALESCE(SUM(change_value),0) FROM bonuses WHERE create_time >= ? AND create_time < ?", (start, end)
        ).fetchone()[0]
        print(f"  wallet_transactions rows: {wt_count}, distinct users: {wt_users}")
        print(f"  bonuses rows: {bonus_count}, distinct users: {bonus_users}, total value: {bonus_amt}")
        if bonus_count:
            cats = cur.execute(
                "SELECT matched_category, COUNT(*), SUM(change_value) FROM bonuses "
                "WHERE create_time >= ? AND create_time < ? GROUP BY matched_category ORDER BY COUNT(*) DESC",
                (start, end),
            ).fetchall()
            for row in cats:
                print("   ", row)

    print("\n=== hourly wallet_transactions row counts, last 8 hours (by create_time hour, raw string) ===")
    for row in cur.execute(
        "SELECT substr(create_time,1,13) AS hr, COUNT(*), COUNT(DISTINCT user_id) FROM wallet_transactions "
        "WHERE create_time >= ? GROUP BY hr ORDER BY hr",
        ((now_utc - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S"),),
    ).fetchall():
        print(" ", row)

    print("\n=== sample of 10 wallet_transactions rows from the busiest recent hour, to inspect game_name/source pattern ===")
    busiest = cur.execute(
        "SELECT substr(create_time,1,13) AS hr, COUNT(*) c FROM wallet_transactions "
        "WHERE create_time >= ? GROUP BY hr ORDER BY c DESC LIMIT 1",
        ((now_utc - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S"),),
    ).fetchone()
    if busiest:
        hr = busiest[0]
        print(f"  busiest hour: {hr} ({busiest[1]} rows)")
        for row in cur.execute(
            "SELECT id, user_id, game_name, source, source_id, change_value, direction, create_time FROM wallet_transactions "
            "WHERE substr(create_time,1,13) = ? ORDER BY create_time LIMIT 10",
            (hr,),
        ).fetchall():
            print("   ", row)

    conn.close()


if __name__ == "__main__":
    main()
