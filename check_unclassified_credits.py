"""Follow-up 2: break down the unclassified 4-5AM blank-game_name credit
set by source_id PREFIX PATTERN (not exact value), since the exact-value
counter mixed two apparently-different label shapes together
(SYSTEM_AGENT:<user_id>:<timestamp>:<random>, all count=1 since each has
a unique random suffix; DI<date><seq>, count=2 each) -- need the real
proportion of each to know which one actually explains the bulk of the
546-user spike.
"""
import os
import re
import sqlite3
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


def prefix_pattern(source_id):
    if source_id is None:
        return "(NULL)"
    if source_id.startswith("SYSTEM_AGENT:"):
        return "SYSTEM_AGENT:<user_id>:<timestamp>:<random>"
    if re.match(r"^DI\d{16}$", source_id):
        return "DI<16 digits> (deposit-order-shaped)"
    if re.match(r"^DI\d+", source_id):
        return "DI<other digit count>"
    # Fallback: strip trailing digits/hex to get a rough prefix bucket
    stripped = re.sub(r"[0-9]+$", "", source_id)
    return f"OTHER, stripped-trailing-digits prefix: {stripped!r}"


def main():
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    s3.download_file(bucket, "daily_records.db", DAILY_DB)

    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()

    START, END = "2026-08-08 04:00:00", "2026-08-08 05:00:00"

    rows = cur.execute(
        "SELECT w.source_id, w.user_id, w.change_value FROM wallet_transactions w "
        "WHERE w.create_time >= ? AND w.create_time < ? AND (w.game_name IS NULL OR w.game_name = '') "
        "AND NOT EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id)",
        (START, END),
    ).fetchall()

    pattern_counter = Counter()
    pattern_users = {}
    pattern_amount = Counter()
    for source_id, user_id, change_value in rows:
        p = prefix_pattern(source_id)
        pattern_counter[p] += 1
        pattern_users.setdefault(p, set()).add(user_id)
        pattern_amount[p] += change_value or 0.0

    print(f"=== {len(rows)} total unclassified rows, broken down by source_id prefix pattern ===")
    for p, cnt in pattern_counter.most_common():
        print(f"  {p!r}: {cnt} rows, {len(pattern_users[p])} distinct users, total change_value {round(pattern_amount[p], 2)}")

    print("\n=== sample of 10 'DI...'-pattern rows (to see if these are actually deposit confirmations, unrelated to the 4:00:00 burst) ===")
    for row in cur.execute(
        "SELECT w.id, w.user_id, w.source_id, w.change_value, w.create_time FROM wallet_transactions w "
        "WHERE w.create_time >= ? AND w.create_time < ? AND (w.game_name IS NULL OR w.game_name = '') "
        "AND w.source_id LIKE 'DI%' AND NOT EXISTS (SELECT 1 FROM bonuses b WHERE b.id = w.id) "
        "ORDER BY w.create_time LIMIT 10",
        (START, END),
    ).fetchall():
        print("  ", row)

    print("\n=== SYSTEM_AGENT rows: change_value vs user's CURRENT wallet balance (is it proportional -- i.e. interest?) ===")
    sample = cur.execute(
        "SELECT w.user_id, w.change_value, w.change_after FROM wallet_transactions w "
        "WHERE w.create_time >= ? AND w.create_time < ? AND w.source_id LIKE 'SYSTEM_AGENT:%' "
        "ORDER BY w.create_time LIMIT 15",
        (START, END),
    ).fetchall()
    for user_id, change_value, change_after in sample:
        ratio = (change_value / change_after * 100) if change_after else None
        print(f"   user={user_id} credited={change_value} balance_after_prior_row(change_after)={change_after} ratio%={round(ratio,3) if ratio is not None else None}")

    conn.close()


if __name__ == "__main__":
    main()
