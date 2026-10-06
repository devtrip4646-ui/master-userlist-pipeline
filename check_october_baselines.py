"""One-off read-only diagnostic: baselines used to set the October 2026
targets -- daily deposit/new/old/withdrawal/bonus-cost table, cohort-based
new-user retention (D1/D2/D3/D7/D15, both exact-day and by-day variants),
reactivation counts (old depositor with no deposit in the previous 14 days),
agent_performance category rates from master_userlist.db, and withdrawal
processing-time share. Today (IST, still accumulating) is excluded from
every aggregate. Always writes debug/october_baselines.json (including a
traceback on failure) and commits it. One-off; delete this script and its
workflow after use.
"""
import json
import os
import sqlite3
import subprocess
import traceback
from collections import defaultdict
from datetime import datetime, timedelta

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")
MASTER_DB = os.path.join(BASE, "master_userlist.db")
RETENTION_DAYS = (1, 2, 3, 7, 15)
LAPSE_DAYS = 14


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace(" ", "T"))
    except ValueError:
        return None


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def run(result):
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    s3.download_file(bucket, "daily_records.db", DAILY_DB)
    s3.download_file(bucket, "master_userlist.db", MASTER_DB)

    today = (datetime.utcnow() + timedelta(hours=5, minutes=30)).date()
    today_s = today.isoformat()
    result["today_excluded"] = today_s

    conn = sqlite3.connect(DAILY_DB)
    deposits = conn.execute(
        "SELECT user_id, order_amount, substr(create_time,1,10), is_first_deposit FROM deposits "
        "WHERE status = 'COMPLETE' AND user_id IS NOT NULL AND substr(create_time,1,10) < ?",
        (today_s,),
    ).fetchall()
    wd_rows = conn.execute(
        "SELECT withdraw_amount, substr(create_time,1,10), status, review_time, update_time FROM withdrawals "
        "WHERE substr(create_time,1,10) < ?",
        (today_s,),
    ).fetchall()
    bonus_rows = conn.execute(
        "SELECT substr(create_time,1,10), SUM(change_value) FROM bonuses "
        "WHERE matched_category IS NOT NULL AND substr(create_time,1,10) < ? GROUP BY 1",
        (today_s,),
    ).fetchall()
    conn.close()

    dates = sorted({r[2] for r in deposits if r[2]})
    result["window"] = {"first": dates[0], "last": dates[-1], "days": len(dates)}
    date_set = set(dates)

    dep_by_day = defaultdict(lambda: {"amount": 0.0, "orders": 0, "users": set(), "new": set(), "new_amount": 0.0})
    users_by_day = defaultdict(set)
    first_day_orders = defaultdict(lambda: defaultdict(int))  # cohort day -> user -> orders that day
    for uid, amt, day, is_fd in deposits:
        b = dep_by_day[day]
        b["amount"] += amt or 0.0
        b["orders"] += 1
        b["users"].add(uid)
        users_by_day[day].add(uid)
        if is_fd == 1:
            b["new"].add(uid)
            b["new_amount"] += amt or 0.0
        first_day_orders[day][uid] += 1

    wd_by_day = defaultdict(float)
    tat = defaultdict(lambda: [0, 0])
    for amt, day, status, rv, up in wd_rows:
        if status == 2:
            wd_by_day[day] += amt or 0.0
            rdt, udt = parse_dt(rv), parse_dt(up)
            if rdt and udt:
                hrs = max((udt - rdt).total_seconds() / 3600.0, 0)
                tat[day][0 if hrs <= 4 else 1] += 1
    bonus_by_day = {day: v or 0.0 for day, v in bonus_rows}

    daily = []
    for day in dates:
        b = dep_by_day[day]
        old_users = b["users"] - b["new"]
        old_amount = b["amount"] - b["new_amount"]
        daily.append({
            "date": day,
            "total_deposit": round(b["amount"], 2),
            "orders": b["orders"],
            "depositors": len(b["users"]),
            "new_users": len(b["new"]),
            "old_users": len(old_users),
            "new_user_deposit": round(b["new_amount"], 2),
            "old_user_deposit": round(old_amount, 2),
            "avg_deposit_per_depositor": round(b["amount"] / len(b["users"]), 2) if b["users"] else 0.0,
            "avg_deposit_old_user": round(old_amount / len(old_users), 2) if old_users else 0.0,
            "withdrawals_completed": round(wd_by_day.get(day, 0.0), 2),
            "hold_pct": round((1 - wd_by_day.get(day, 0.0) / b["amount"]) * 100, 2) if b["amount"] else None,
            "bonus_value": round(bonus_by_day.get(day, 0.0), 2),
            "bonus_pct_of_deposit": round(bonus_by_day.get(day, 0.0) / b["amount"] * 100, 2) if b["amount"] else None,
            "wd_under_4h": tat[day][0],
            "wd_over_4h": tat[day][1],
        })
    result["daily"] = daily

    # Same-day (day 0) repeat: share of new users with 2+ deposit orders on their first day.
    d0 = []
    for day in dates:
        new_users = dep_by_day[day]["new"]
        if new_users:
            rep = sum(1 for u in new_users if first_day_orders[day][u] >= 2)
            d0.append({"date": day, "new_users": len(new_users), "d0_repeat_users": rep})
    result["d0_repeat"] = d0

    # Cohort retention. Cohort = users with a first deposit on day c. Retained at day N =
    # deposited on exactly c+N ("exact"), or on any day c+1..c+N ("by"). A cohort only counts
    # once c+N is a fully-observed day (<= last full day).
    last_day = d(dates[-1])
    cohorts = []
    for day in dates:
        s = dep_by_day[day]["new"]
        if not s:
            continue
        c = d(day)
        row = {"date": day, "cohort": len(s)}
        for n in RETENTION_DAYS:
            target = (c + timedelta(days=n))
            if target > last_day:
                row[f"exact_d{n}"] = None
                row[f"by_d{n}"] = None
                continue
            exact = len(s & users_by_day.get(target.isoformat(), set()))
            by = set()
            for k in range(1, n + 1):
                by |= users_by_day.get((c + timedelta(days=k)).isoformat(), set())
            row[f"exact_d{n}"] = exact
            row[f"by_d{n}"] = len(s & by)
        cohorts.append(row)
    result["cohorts"] = cohorts

    # Reactivation: depositor on day d, not a first-deposit that day, with no deposit in the
    # previous LAPSE_DAYS days. Only evaluable when d - LAPSE_DAYS is inside the observed window.
    first_obs = d(dates[0])
    react = []
    for day in dates:
        dd = d(day)
        if dd - timedelta(days=LAPSE_DAYS) < first_obs:
            continue
        prior = set()
        for k in range(1, LAPSE_DAYS + 1):
            prior |= users_by_day.get((dd - timedelta(days=k)).isoformat(), set())
        old_today = users_by_day[day] - dep_by_day[day]["new"]
        reactivated = old_today - prior
        amt = sum(a for (u, a, dy, fd) in deposits if dy == day and u in reactivated)
        react.append({"date": day, "reactivated_users": len(reactivated), "old_depositors": len(old_today),
                      "reactivated_deposit": round(amt, 2)})
    result["reactivation"] = react

    # Agent performance categories (Performance page) -- last 28 observed days.
    perf = {}
    try:
        mconn = sqlite3.connect(MASTER_DB)
        cutoff = (today - timedelta(days=28)).isoformat()
        rows = mconn.execute(
            "SELECT category, date, SUM(numerator), SUM(denominator) FROM agent_performance "
            "WHERE date >= ? AND date < ? GROUP BY category, date",
            (cutoff, today_s),
        ).fetchall()
        mconn.close()
        cat = defaultdict(list)
        for c, dy, num, den in rows:
            cat[c].append({"date": dy, "numerator": num or 0, "denominator": den or 0})
        for c, items in cat.items():
            items.sort(key=lambda r: r["date"])
            last14 = items[-14:]
            perf[c] = {
                "days": len(items),
                "num_total_28d": round(sum(i["numerator"] for i in items), 2),
                "den_total_28d": round(sum(i["denominator"] for i in items), 2),
                "num_total_last14": round(sum(i["numerator"] for i in last14), 2),
                "den_total_last14": round(sum(i["denominator"] for i in last14), 2),
                "daily": items,
            }
    except Exception as e:  # table may not exist yet
        perf = {"error": f"{type(e).__name__}: {e}"}
    result["agent_performance"] = perf

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
    with open(os.path.join(out_path, "october_baselines.json"), "w") as f:
        json.dump(result, f, indent=1, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "-f", "debug/october_baselines.json"], check=True)
    commit = subprocess.run(["git", "commit", "-m", "debug: october baselines"])
    if commit.returncode == 0:
        for attempt in range(5):
            push = subprocess.run(["git", "push"])
            if push.returncode == 0:
                break
            subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        else:
            raise RuntimeError("git push failed after 5 rebase retries")
    print(json.dumps({k: v for k, v in result.items() if k not in ("daily", "cohorts", "reactivation", "agent_performance", "d0_repeat")}, indent=1, default=str))

    if result.get("status") != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
