"""One-off report generator: for every day in September 2026, the total
value paid for "New Users Lossback" and "Recovery Bonus" separately, plus
a combined total of the two -- no per-user detail. Produces an .xlsx,
committed into the repo so it can be pulled and handed to the user. Always
writes debug/gen_sep_lossback_recovery_report.json (including a traceback
on failure) and commits both, since GitHub Actions logs for this repo
aren't readable without signing in. One-off; delete this script and its
workflow after use.
"""
import json
import os
import sqlite3
import subprocess
import traceback
from collections import defaultdict

import boto3
import openpyxl

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")
OUT_XLSX = os.path.join(BASE, "debug", "sep_lossback_recovery_report.xlsx")

WINDOW_START = "2026-09-01"
WINDOW_END_EXCLUSIVE = "2026-10-01"
CATEGORIES = ["New Users Lossback", "Recovery Bonus"]


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

    result["window"] = {"start": WINDOW_START, "end_exclusive": WINDOW_END_EXCLUSIVE}

    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()
    placeholders = ",".join("?" * len(CATEGORIES))
    rows = cur.execute(
        f"SELECT substr(create_time, 1, 10) AS day, matched_category, SUM(change_value) "
        f"FROM bonuses WHERE matched_category IN ({placeholders}) "
        "AND substr(create_time, 1, 10) >= ? AND substr(create_time, 1, 10) < ? "
        "GROUP BY day, matched_category",
        (*CATEGORIES, WINDOW_START, WINDOW_END_EXCLUSIVE),
    ).fetchall()
    conn.close()
    result["row_count"] = len(rows)

    by_day = defaultdict(lambda: {c: 0.0 for c in CATEGORIES})
    for day, category, value in rows:
        by_day[day][category] = round(value or 0.0, 2)

    table_rows = []
    for day in sorted(by_day.keys()):
        vals = by_day[day]
        combined = round(sum(vals.values()), 2)
        table_rows.append({"date": day, **vals, "combined_total": combined})

    result["distinct_days"] = len(table_rows)
    result["grand_total_new_users_lossback"] = round(sum(r["New Users Lossback"] for r in table_rows), 2)
    result["grand_total_recovery_bonus"] = round(sum(r["Recovery Bonus"] for r in table_rows), 2)
    result["grand_total_combined"] = round(sum(r["combined_total"] for r in table_rows), 2)

    os.makedirs(os.path.dirname(OUT_XLSX), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sep Lossback + Recovery"
    ws.append(["Date", "New Users Lossback", "Recovery Bonus", "Combined Total"])
    for r in table_rows:
        ws.append([r["date"], r["New Users Lossback"], r["Recovery Bonus"], r["combined_total"]])
    ws.append([
        "TOTAL", result["grand_total_new_users_lossback"], result["grand_total_recovery_bonus"],
        result["grand_total_combined"],
    ])
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
    with open(os.path.join(out_path, "gen_sep_lossback_recovery_report.json"), "w") as f:
        json.dump({k: v for k, v in result.items() if k != "xlsx_path"}, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "-f", "debug/gen_sep_lossback_recovery_report.json"], check=True)
    if result.get("status") == "success":
        subprocess.run(["git", "add", "-f", OUT_XLSX], check=True)
    commit = subprocess.run(["git", "commit", "-m", "debug: sep lossback + recovery report"])
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
