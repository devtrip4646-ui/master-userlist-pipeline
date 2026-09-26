"""One-off report generator: for every day from 2026-09-01 through
yesterday, the total number of claims and total value paid per bonus
category (matched_category from the `bonuses` table) -- no per-user detail.
Produces an .xlsx, committed into the repo so it can be pulled and handed
to the user. Always writes debug/gen_daily_bonus_report.json (including a
traceback on failure) and commits both, since GitHub Actions logs for this
repo aren't readable without signing in. One-off; delete this script and
its workflow after use.
"""
import json
import os
import sqlite3
import subprocess
import traceback
from collections import defaultdict
from datetime import datetime, timedelta

import boto3
import openpyxl

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")
OUT_XLSX = os.path.join(BASE, "debug", "daily_bonus_report.xlsx")

WINDOW_START = "2026-09-01"


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def run(result):
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    s3.download_file(bucket, "daily_records.db", DAILY_DB)

    today_ist = (datetime.utcnow() + timedelta(hours=5, minutes=30)).date().isoformat()
    result["window"] = {"start": WINDOW_START, "end_exclusive": today_ist}

    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT substr(create_time, 1, 10) AS day, matched_category, COUNT(*), SUM(change_value) "
        "FROM bonuses WHERE matched_category IS NOT NULL "
        "AND substr(create_time, 1, 10) >= ? AND substr(create_time, 1, 10) < ? "
        "GROUP BY day, matched_category",
        (WINDOW_START, today_ist),
    ).fetchall()
    conn.close()
    result["row_count"] = len(rows)

    table_rows = [
        {"date": day, "bonus_category": category, "claimed_count": count, "total_value": round(value or 0.0, 2)}
        for day, category, count, value in rows
    ]
    table_rows.sort(key=lambda r: (r["date"], -r["total_value"]))
    result["distinct_days"] = len({r["date"] for r in table_rows})
    result["distinct_categories"] = len({r["bonus_category"] for r in table_rows})
    result["grand_total_value"] = round(sum(r["total_value"] for r in table_rows), 2)

    os.makedirs(os.path.dirname(OUT_XLSX), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Daily Bonus Report"
    ws.append(["Date", "Bonus Category", "Claimed Count", "Total Value"])
    for r in table_rows:
        ws.append([r["date"], r["bonus_category"], r["claimed_count"], r["total_value"]])
    wb.save(OUT_XLSX)
    result["xlsx_path"] = OUT_XLSX
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
    with open(os.path.join(out_path, "gen_daily_bonus_report.json"), "w") as f:
        json.dump({k: v for k, v in result.items() if k != "xlsx_path"}, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "-f", "debug/gen_daily_bonus_report.json"], check=True)
    if result.get("status") == "success":
        subprocess.run(["git", "add", "-f", OUT_XLSX], check=True)
    commit = subprocess.run(["git", "commit", "-m", "debug: daily bonus report"])
    if commit.returncode == 0:
        for attempt in range(5):
            push = subprocess.run(["git", "push"])
            if push.returncode == 0:
                break
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        else:
            raise RuntimeError("git push failed after 5 rebase retries")
    print(json.dumps({k: v for k, v in result.items() if k != "xlsx_path"}, indent=2, default=str))

    if result.get("status") != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
