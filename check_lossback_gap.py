"""One-off read-only diagnostic: New Users Lossback bonuses vanished from
the bonuses table starting ~2026-09-19, even though raw wallet_transactions
still shows lossback-tagged rows. Checks: (1) which game_name wrapper these
rows actually use now, (2) whether they exist in wallet_transactions but
are missing from bonuses (classification never ran on them), and (3) the
backfill watermark state, to see if it's stuck. Writes
debug/lossback_gap.json and commits it back to the repo. One-off; delete
this script and its workflow after use.
"""
import json
import os
import sqlite3
import subprocess

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

    result = {}

    # 1. Which game_name wrapper carries "New Users Lossback" source_id rows, by day.
    rows = cur.execute(
        "SELECT game_name, substr(create_time, 1, 10) as day, COUNT(*), MIN(id), MAX(id) "
        "FROM wallet_transactions WHERE source_id LIKE 'New Users Lossback%' "
        "GROUP BY game_name, day ORDER BY day"
    ).fetchall()
    result["lossback_rows_by_game_name_and_day"] = [
        {"game_name": g, "day": d, "count": c, "min_id": mn, "max_id": mx} for g, d, c, mn, mx in rows
    ]

    # 2. For each of those rows, do they have a matching bonuses row (by id)?
    missing_by_day = {}
    for game_name, day, count, min_id, max_id in rows:
        wt_ids = {r[0] for r in cur.execute(
            "SELECT id FROM wallet_transactions WHERE game_name = ? AND substr(create_time,1,10) = ? "
            "AND source_id LIKE 'New Users Lossback%'",
            (game_name, day),
        ).fetchall()}
        if not wt_ids:
            continue
        placeholders = ",".join("?" * len(wt_ids))
        bonus_ids = {r[0] for r in cur.execute(
            f"SELECT id FROM bonuses WHERE id IN ({placeholders})", list(wt_ids)
        ).fetchall()}
        missing = wt_ids - bonus_ids
        missing_by_day[f"{game_name}|{day}"] = {"total": len(wt_ids), "missing_from_bonuses": len(missing)}
    result["missing_from_bonuses_by_game_and_day"] = missing_by_day

    # 3. Backfill watermark state.
    try:
        backfill_rows = cur.execute("SELECT key, value FROM backfill_state").fetchall()
        result["backfill_state"] = dict(backfill_rows)
    except sqlite3.OperationalError as e:
        result["backfill_state_error"] = str(e)

    # 4. Max wallet_transactions id overall, for comparison against the watermark.
    result["max_wallet_transactions_id"] = cur.execute("SELECT MAX(id) FROM wallet_transactions").fetchone()[0]
    result["max_bonuses_id"] = cur.execute("SELECT MAX(id) FROM bonuses").fetchone()[0]

    # 5. Sample a few "missing" rows in full, for the most recent affected day, to inspect raw fields.
    if rows:
        last_game_name, last_day = rows[-1][0], rows[-1][1]
        samples = cur.execute(
            "SELECT id, game_name, source, source_id, user_id, change_value, create_time FROM wallet_transactions "
            "WHERE game_name = ? AND substr(create_time,1,10) = ? AND source_id LIKE 'New Users Lossback%' "
            "ORDER BY id DESC LIMIT 5",
            (last_game_name, last_day),
        ).fetchall()
        result["sample_rows_most_recent_day"] = [
            {"id": i, "game_name": g, "source": s, "source_id": sid, "user_id": u, "change_value": cv, "create_time": ct}
            for i, g, s, sid, u, cv, ct in samples
        ]

    conn.close()

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "lossback_gap.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/lossback_gap.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: New Users Lossback classification gap", "--allow-empty"], check=True)

    for attempt in range(5):
        push = subprocess.run(["git", "push"], capture_output=True, text=True)
        if push.returncode == 0:
            break
        print(f"push attempt {attempt + 1} failed, rebasing and retrying:\n{push.stderr}")
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
    else:
        raise RuntimeError("git push failed after 5 rebase-and-retry attempts")

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
