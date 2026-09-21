"""One-off read-only diagnostic: compute current-state KPI numbers (retention,
reactivation, churn, deposit conversion, hold %, VIP mix, agent coverage,
bonus participation) from master_userlist.db (users.create_time = registration,
users.last_active_time = most recent activity -- NOT purged, unlike
daily_records.db's 32-day rolling window) and daily_records.db (deposits/
withdrawals/wallet_transactions, last ~32 days only).

Writes debug/kpi_snapshot.json and commits it. One-off; delete this script
and its workflow after use.
"""
import json
import os
import sqlite3
import subprocess
import traceback
from datetime import datetime, timedelta

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")
DAILY_DB = os.path.join(BASE, "daily_records.db")


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def safe(result, key, fn):
    try:
        result[key] = fn()
    except Exception:
        result[key] = {"error": traceback.format_exc()[-1500:]}


def main():
    result = {}
    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()
    s3.download_file(bucket, "master_userlist.db", MASTER_DB)
    s3.download_file(bucket, "daily_records.db", DAILY_DB)

    mconn = sqlite3.connect(MASTER_DB)
    mcur = mconn.cursor()
    dconn = sqlite3.connect(DAILY_DB)
    dcur = dconn.cursor()

    now = datetime.utcnow()
    d7 = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    d14 = (now - timedelta(days=14)).strftime("%Y-%m-%d %H:%M:%S")
    d21 = (now - timedelta(days=21)).strftime("%Y-%m-%d %H:%M:%S")
    d30 = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    d32 = (now - timedelta(days=32)).strftime("%Y-%m-%d %H:%M:%S")
    d60 = (now - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
    result["as_of_utc"] = now.strftime("%Y-%m-%d %H:%M:%S")

    def total_users():
        return mcur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    safe(result, "total_registered_users", total_users)

    def active_rate(cutoff):
        n = mcur.execute("SELECT COUNT(*) FROM users WHERE last_active_time >= ?", (cutoff,)).fetchone()[0]
        total = result["total_registered_users"]
        return {"active_users": n, "total_users": total, "pct": round(100 * n / total, 3) if total else None}
    safe(result, "active_rate_7d", lambda: active_rate(d7))
    safe(result, "active_rate_30d", lambda: active_rate(d30))

    def new_regs_30d():
        return mcur.execute("SELECT COUNT(*) FROM users WHERE create_time >= ?", (d30,)).fetchone()[0]
    safe(result, "new_registrations_30d", new_regs_30d)

    def day7_retention():
        cohort_start = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        cohort_end = (now - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
        cohort = mcur.execute(
            "SELECT COUNT(*) FROM users WHERE create_time >= ? AND create_time < ?", (cohort_start, cohort_end)
        ).fetchone()[0]
        retained = mcur.execute(
            "SELECT COUNT(*) FROM users WHERE create_time >= ? AND create_time < ? "
            "AND last_active_time >= datetime(create_time, '+7 days')",
            (cohort_start, cohort_end),
        ).fetchone()[0]
        return {"cohort_registered_8_30_days_ago": cohort, "still_active_at_day7": retained,
                "pct": round(100 * retained / cohort, 3) if cohort else None}
    safe(result, "day7_retention_new_users", day7_retention)

    def day30_retention():
        cohort_start = (now - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
        cohort_end = (now - timedelta(days=31)).strftime("%Y-%m-%d %H:%M:%S")
        cohort = mcur.execute(
            "SELECT COUNT(*) FROM users WHERE create_time >= ? AND create_time < ?", (cohort_start, cohort_end)
        ).fetchone()[0]
        retained = mcur.execute(
            "SELECT COUNT(*) FROM users WHERE create_time >= ? AND create_time < ? "
            "AND last_active_time >= datetime(create_time, '+30 days')",
            (cohort_start, cohort_end),
        ).fetchone()[0]
        return {"cohort_registered_31_90_days_ago": cohort, "still_active_at_day30": retained,
                "pct": round(100 * retained / cohort, 3) if cohort else None}
    safe(result, "day30_retention_new_users", day30_retention)

    def churn_30d():
        was_active_31_60 = mcur.execute(
            "SELECT COUNT(*) FROM users WHERE last_active_time >= ? AND last_active_time < ?", (d60, d30)
        ).fetchone()[0]
        return {"note": "users whose most-recent activity falls 31-60 days ago -- i.e. they were "
                         "active-ish but have NOT returned in the last 30 days",
                "churned_users": was_active_31_60}
    safe(result, "churn_signal_30d", churn_30d)

    def reactivation_within_window():
        rows = dcur.execute(
            "SELECT user_id, MIN(create_time), MAX(create_time), COUNT(DISTINCT substr(create_time,1,10)) "
            "FROM wallet_transactions WHERE create_time >= ? GROUP BY user_id", (d32,)
        ).fetchall()
        engaged_base = len(rows)
        recent_active = dcur.execute(
            "SELECT DISTINCT user_id FROM wallet_transactions WHERE create_time >= ?", (d7,)
        ).fetchall()
        recent_active_ids = {r[0] for r in recent_active}
        dormant_gap_ids = dcur.execute(
            "SELECT DISTINCT user_id FROM wallet_transactions WHERE create_time >= ? AND create_time < ?", (d21, d7)
        ).fetchall()
        dormant_gap_ids = {r[0] for r in dormant_gap_ids}
        earlier_active_ids = dcur.execute(
            "SELECT DISTINCT user_id FROM wallet_transactions WHERE create_time >= ? AND create_time < ?", (d32, d21)
        ).fetchall()
        earlier_active_ids = {r[0] for r in earlier_active_ids}
        reactivated = recent_active_ids - dormant_gap_ids
        reactivated = reactivated & earlier_active_ids
        return {
            "note": "proxy only, limited by daily_records.db's 32-day retention: users active in the "
                    "last 7 days, silent for the 14-21 day window, but seen again before that (days 21-32)",
            "engaged_base_32d": engaged_base,
            "reactivated_users": len(reactivated),
            "pct_of_engaged_base": round(100 * len(reactivated) / engaged_base, 3) if engaged_base else None,
        }
    safe(result, "reactivation_signal_32d_window", reactivation_within_window)

    def deposit_conversion_new_users():
        new_dep = dcur.execute(
            "SELECT COUNT(DISTINCT user_id) FROM deposits WHERE status='COMPLETE' AND is_first_deposit=1 "
            "AND create_time >= ?", (d30,)
        ).fetchone()[0]
        new_regs = result.get("new_registrations_30d")
        return {"first_time_depositors_30d": new_dep, "new_registrations_30d": new_regs,
                "pct": round(100 * new_dep / new_regs, 3) if new_regs else None}
    safe(result, "new_user_deposit_conversion_30d", deposit_conversion_new_users)

    def repeat_deposit_rate():
        rows = dcur.execute(
            "SELECT user_id, COUNT(*) FROM deposits WHERE status='COMPLETE' AND create_time >= ? GROUP BY user_id",
            (d30,),
        ).fetchall()
        total_depositors = len(rows)
        repeat = sum(1 for _, c in rows if c > 1)
        return {"depositors_30d": total_depositors, "repeat_depositors_30d": repeat,
                "pct": round(100 * repeat / total_depositors, 3) if total_depositors else None}
    safe(result, "repeat_deposit_rate_30d", repeat_deposit_rate)

    def hold_pct():
        dep_total = dcur.execute(
            "SELECT COALESCE(SUM(order_amount),0) FROM deposits WHERE status='COMPLETE' AND create_time >= ?", (d30,)
        ).fetchone()[0]
        wd_total = dcur.execute(
            "SELECT COALESCE(SUM(withdraw_amount),0) FROM withdrawals WHERE status=2 AND create_time >= ?", (d30,)
        ).fetchone()[0]
        hold = (1 - wd_total / dep_total) * 100 if dep_total else None
        return {"total_deposits_30d": dep_total, "total_withdrawals_30d": wd_total,
                "hold_pct": round(hold, 3) if hold is not None else None}
    safe(result, "deposit_hold_pct_30d", hold_pct)

    def arppu():
        row = dcur.execute(
            "SELECT COALESCE(SUM(order_amount),0), COUNT(DISTINCT user_id) FROM deposits "
            "WHERE status='COMPLETE' AND create_time >= ?", (d30,)
        ).fetchone()
        total, depositors = row
        return {"total_deposit_amount_30d": total, "distinct_depositors_30d": depositors,
                "arppu": round(total / depositors, 2) if depositors else None}
    safe(result, "arppu_30d", arppu)

    def vip_mix():
        rows = mcur.execute(
            "SELECT CASE WHEN vip_level >= 1 THEN 1 ELSE 0 END AS tier, COUNT(*) "
            "FROM users WHERE last_active_time >= ? GROUP BY tier", (d30,)
        ).fetchall()
        d = {("vip1_plus" if k == 1 else "vip0"): v for k, v in rows}
        total = sum(d.values())
        return {**d, "pct_vip1_plus": round(100 * d.get("vip1_plus", 0) / total, 3) if total else None}
    safe(result, "vip_mix_active_30d", vip_mix)

    def agent_coverage():
        try:
            assigned = mcur.execute("SELECT COUNT(*) FROM agent_assignments").fetchone()[0]
        except sqlite3.OperationalError:
            assigned = 0
        total = result.get("total_registered_users")
        return {"assigned_users": assigned, "total_users": total,
                "pct": round(100 * assigned / total, 3) if total else None}
    safe(result, "agent_assignment_coverage", agent_coverage)

    def bonus_participation_30d():
        bonus_users = dcur.execute(
            "SELECT COUNT(DISTINCT w.user_id) FROM bonuses b JOIN wallet_transactions w ON w.id = b.id "
            "WHERE w.create_time >= ?", (d30,)
        ).fetchone()[0]
        active = result.get("active_rate_30d", {}).get("active_users")
        return {"users_with_any_bonus_30d": bonus_users, "active_users_30d": active,
                "pct_of_active": round(100 * bonus_users / active, 3) if active else None}
    safe(result, "bonus_participation_30d", bonus_participation_30d)

    mconn.close()
    dconn.close()

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "kpi_snapshot.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/kpi_snapshot.json"], check=True)
    commit = subprocess.run(["git", "commit", "-m", "debug: KPI snapshot for 30-day target sheet"])
    if commit.returncode == 0:
        subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
