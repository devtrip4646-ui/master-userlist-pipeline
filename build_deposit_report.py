"""
Builds an aggregated deposit report -- channel-wise, amount-range, hourly
breakdowns, and success-rate analysis (total vs completed, by amount range /
channel / hour) -- bucketed per calendar date, from the deposits table and
uploads it as JSON to R2 for the "04-project-performance" dashboard Worker.

Usage: python3 build_deposit_report.py
Requires daily_records.db to be present locally (already downloaded by the
caller) and R2 credentials in env vars or .r2_credentials.
"""
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "daily_records.db")

AMOUNT_RANGES = [
    (200, 299),
    (300, 499),
    (500, 999),
    (1000, 1999),
    (2000, 2499),
    (2500, 4999),
    (5000, 9999),
    (10000, 19999),
    (20000, 50000),
]
RANGE_LABELS = [f"{lo}-{hi}" for lo, hi in AMOUNT_RANGES] + ["Other"]


def bucket_for_amount(amount):
    for lo, hi in AMOUNT_RANGES:
        if lo <= amount <= hi:
            return f"{lo}-{hi}"
    return "Other"


def load_creds():
    creds_path = os.path.join(BASE, ".r2_credentials")
    if os.path.exists(creds_path):
        return dict(line.strip().split("=", 1) for line in open(creds_path) if "=" in line)
    return {
        "R2_ACCESS_KEY_ID": os.environ["R2_ACCESS_KEY_ID"],
        "R2_SECRET_ACCESS_KEY": os.environ["R2_SECRET_ACCESS_KEY"],
        "R2_ENDPOINT_URL": os.environ["R2_ENDPOINT_URL"],
        "R2_BUCKET": os.environ["R2_BUCKET"],
    }


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace(" ", "T"))
    except ValueError:
        return None


def aggregate(records):
    """
    records: list of dicts with keys channel, amount, hour, status,
    completion_minutes, user_id. Returns all report sections for this scope.
    """
    completed = [r for r in records if r["status"] == "COMPLETE"]

    # --- completed-only breakdowns (money/volume of successful deposits) ---
    by_channel = {}
    by_range = {label: {"count": 0, "total_amount": 0.0, "users": set()} for label in RANGE_LABELS}
    by_channel_and_range = {}
    hourly = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"count": 0, "total_amount": 0.0})))
    total_count, total_amount = 0, 0.0

    for r in completed:
        channel, amount, hour = r["channel"], r["amount"], r["hour"]
        rlabel = bucket_for_amount(amount)
        total_count += 1
        total_amount += amount

        ch = by_channel.setdefault(channel, {"count": 0, "total_amount": 0.0})
        ch["count"] += 1
        ch["total_amount"] += amount

        by_range[rlabel]["count"] += 1
        by_range[rlabel]["total_amount"] += amount
        if r["user_id"] is not None:
            by_range[rlabel]["users"].add(r["user_id"])

        cr = by_channel_and_range.setdefault((channel, rlabel), {"count": 0, "total_amount": 0.0})
        cr["count"] += 1
        cr["total_amount"] += amount

        if hour is not None:
            hcr = hourly[hour][channel][rlabel]
            hcr["count"] += 1
            hcr["total_amount"] += amount

    # --- success-rate breakdowns (all statuses vs completed) ---
    succ_range = {label: {"total": 0, "completed": 0, "min_sum": 0.0, "min_n": 0} for label in RANGE_LABELS}
    succ_channel = {}
    hourly_succ_channel = defaultdict(lambda: defaultdict(lambda: {"total": 0, "completed": 0}))
    hourly_succ_range = defaultdict(lambda: defaultdict(lambda: {"total": 0, "completed": 0}))

    for r in records:
        channel, amount, hour = r["channel"], r["amount"], r["hour"]
        rlabel = bucket_for_amount(amount)
        is_completed = r["status"] == "COMPLETE"

        sr = succ_range[rlabel]
        sr["total"] += 1
        if is_completed:
            sr["completed"] += 1
            if r["completion_minutes"] is not None:
                sr["min_sum"] += r["completion_minutes"]
                sr["min_n"] += 1

        sc = succ_channel.setdefault(channel, {
            "total": 0, "completed": 0, "completed_users": set(), "completed_amount": 0.0, "min_sum": 0.0, "min_n": 0
        })
        sc["total"] += 1
        if is_completed:
            sc["completed"] += 1
            sc["completed_amount"] += amount
            if r["user_id"] is not None:
                sc["completed_users"].add(r["user_id"])
            if r["completion_minutes"] is not None:
                sc["min_sum"] += r["completion_minutes"]
                sc["min_n"] += 1

        if hour is not None:
            hsc = hourly_succ_channel[hour][channel]
            hsc["total"] += 1
            if is_completed:
                hsc["completed"] += 1
            hsr = hourly_succ_range[hour][rlabel]
            hsr["total"] += 1
            if is_completed:
                hsr["completed"] += 1

    def pct(completed, total):
        return round(completed / total * 100, 1) if total else 0

    return {
        "totals": {"count": total_count, "total_amount": round(total_amount, 2)},
        "by_channel": [
            {
                "channel": ch,
                "count": v["count"],
                "total_amount": round(v["total_amount"], 2),
                "avg_amount": round(v["total_amount"] / v["count"], 2) if v["count"] else 0,
            }
            for ch, v in sorted(by_channel.items(), key=lambda x: -x[1]["total_amount"])
        ],
        "by_amount_range": [
            {
                "range": label,
                "count": by_range[label]["count"],
                "users": len(by_range[label]["users"]),
                "total_amount": round(by_range[label]["total_amount"], 2),
            }
            for label in RANGE_LABELS
        ],
        "by_channel_and_range": [
            {"channel": ch, "range": rl, "count": v["count"], "total_amount": round(v["total_amount"], 2)}
            for (ch, rl), v in sorted(by_channel_and_range.items(), key=lambda x: -x[1]["total_amount"])
        ],
        "hourly": [
            {
                "hour": hour,
                "channel": ch,
                "range": rl,
                "count": v["count"],
                "total_amount": round(v["total_amount"], 2),
            }
            for hour, chans in sorted(hourly.items())
            for ch, ranges in chans.items()
            for rl, v in ranges.items()
        ],
        "success_by_range": [
            {
                "range": label,
                "total": v["total"],
                "completed": v["completed"],
                "success_pct": pct(v["completed"], v["total"]),
                "avg_minutes": round(v["min_sum"] / v["min_n"], 1) if v["min_n"] else None,
            }
            for label, v in succ_range.items()
        ],
        "success_by_channel": [
            {
                "channel": ch,
                "total": v["total"],
                "comp_orders": v["completed"],
                "comp_users": len(v["completed_users"]),
                "comp_amount": round(v["completed_amount"], 2),
                "success_pct": pct(v["completed"], v["total"]),
                "avg_minutes": round(v["min_sum"] / v["min_n"], 1) if v["min_n"] else None,
            }
            for ch, v in sorted(succ_channel.items(), key=lambda x: -x[1]["completed_amount"])
        ],
        "hourly_success_by_channel": [
            {"hour": hour, "channel": ch, "total": v["total"], "completed": v["completed"], "success_pct": pct(v["completed"], v["total"])}
            for hour, chans in sorted(hourly_succ_channel.items())
            for ch, v in chans.items()
        ],
        "hourly_success_by_range": [
            {"hour": hour, "range": rl, "total": v["total"], "completed": v["completed"], "success_pct": pct(v["completed"], v["total"])}
            for hour, ranges in sorted(hourly_succ_range.items())
            for rl, v in ranges.items()
        ],
    }


# Withdrawal status codes: 0 In-Review, 1 Processing, 2 Complete, 3 Rejected, 4 Failed
ACTIVE_WITHDRAW_STATUSES = (0, 1, 2)


def summarize(deposit_records, withdrawal_records, bet_user_ids):
    completed_deposits = [r for r in deposit_records if r["status"] == "COMPLETE"]
    active_withdrawals = [r for r in withdrawal_records if r["status"] in ACTIVE_WITHDRAW_STATUSES]

    total_deposit = round(sum(r["amount"] for r in completed_deposits), 2)
    total_withdraw = round(sum(r["amount"] for r in active_withdrawals), 2)
    deposit_users = {r["user_id"] for r in completed_deposits if r["user_id"] is not None}
    withdraw_users = {r["user_id"] for r in active_withdrawals if r["user_id"] is not None}
    active_users = deposit_users | withdraw_users | bet_user_ids

    return {
        "total_deposit": total_deposit,
        "total_withdraw": total_withdraw,
        "deposit_orders": len(completed_deposits),
        "withdraw_orders": len(active_withdrawals),
        "deposit_users": len(deposit_users),
        "withdraw_users": len(withdraw_users),
        "active_users": len(active_users),
        "difference": round(total_deposit - total_withdraw, 2),
        "withdraw_deposit_pct": round(total_withdraw / total_deposit * 100, 1) if total_deposit else None,
        # kept for backward compatibility with the KPI cards
        "total_users": len(deposit_users),
        "total_orders": len(completed_deposits),
        "profit": round(total_deposit - total_withdraw, 2),
    }


PROCESSING_TIME_BUCKETS = ["<1h", "1-3h", "3-6h", "6-12h", ">12h"]


def processing_time_bucket(hours):
    if hours < 1:
        return "<1h"
    if hours < 3:
        return "1-3h"
    if hours < 6:
        return "3-6h"
    if hours < 12:
        return "6-12h"
    return ">12h"


PROCESSING_BACKLOG_BUCKETS = ["3-6h", "6-12h", "12-24h", ">24h"]


def processing_backlog_bucket(hours):
    if hours < 3:
        return None
    if hours < 6:
        return "3-6h"
    if hours < 12:
        return "6-12h"
    if hours < 24:
        return "12-24h"
    return ">24h"


INREVIEW_BACKLOG_BUCKETS = ["1-3h", "3-6h", ">6h"]


def inreview_backlog_bucket(hours):
    if hours < 1:
        return None
    if hours < 3:
        return "1-3h"
    if hours < 6:
        return "3-6h"
    return ">6h"


def withdrawal_review_by_channel(withdrawal_full_records):
    """Channel x processing-time-bucket matrix for orders currently in Payment
    Processing (status=1), duration measured strictly from create_time to
    review_time (no update_time fallback -- these orders haven't completed yet)."""
    matrix = defaultdict(lambda: defaultdict(int))
    for r in withdrawal_full_records:
        if r["status"] != 1:
            continue
        if not r["create_dt"] or not r["review_dt"]:
            continue
        hours = max((r["review_dt"] - r["create_dt"]).total_seconds() / 3600.0, 0)
        bucket = processing_time_bucket(hours)
        matrix[r["channel"]][bucket] += 1
    return [
        {"channel": ch, "bucket": b, "count": matrix[ch][b]}
        for ch in sorted(matrix.keys())
        for b in PROCESSING_TIME_BUCKETS
    ]


def withdrawal_completion_by_channel(withdrawal_full_records):
    """Channel x processing-time-bucket matrix for Completed (status=2) withdrawals,
    duration measured from review_time to update_time (the payout step, after review)."""
    matrix = defaultdict(lambda: defaultdict(int))
    for r in withdrawal_full_records:
        if r["status"] != 2:
            continue
        if not r["review_dt"] or not r["update_dt"]:
            continue
        hours = max((r["update_dt"] - r["review_dt"]).total_seconds() / 3600.0, 0)
        bucket = processing_time_bucket(hours)
        matrix[r["channel"]][bucket] += 1
    return [
        {"channel": ch, "bucket": b, "count": matrix[ch][b]}
        for ch in sorted(matrix.keys())
        for b in PROCESSING_TIME_BUCKETS
    ]


def withdrawal_backlog(withdrawal_full_records, now, status, bucket_fn, bucket_labels):
    """Snapshot (as of `now`) of orders currently sitting in `status`, aged from create_time."""
    counts = {label: 0 for label in bucket_labels}
    for r in withdrawal_full_records:
        if r["status"] != status or not r["create_dt"]:
            continue
        hours = max((now - r["create_dt"]).total_seconds() / 3600.0, 0)
        bucket = bucket_fn(hours)
        if bucket:
            counts[bucket] += 1
    return [{"bucket": label, "count": counts[label]} for label in bucket_labels]


# Cumulative deposit ("experience") required to reach each VIP level, per the
# platform's VIP table. Level N's threshold is the deposit total needed to move
# from level N-1 to level N. Kept in sync with api_pull_ingest.py's copy, which
# uses it to (re)compute vip_level in master_userlist.db on every pull.
VIP_THRESHOLDS = {
    0: 0, 1: 200, 2: 1500, 3: 9600, 4: 19600, 5: 95600, 6: 295600, 7: 795600,
    8: 1795600, 9: 3795600, 10: 8795600, 11: 16795600, 12: 28795600,
    13: 44795600, 14: 69795600, 15: 119795600,
}
ACTION_CENTER_LIST_CAP = 500


def action_center_reports(mconn, now):
    """Action Center reports, computed from the master userlist snapshot (not
    date-scoped -- these are lifetime/as-of-last-upload figures, not tied to the
    selected date). Two "near upgrade" lists (users whose remaining deposit gap
    to the next VIP tier is Rs 1-1000 for VIP2-4, Rs 1-50000 for VIP5-15), two
    "inactive" lists (users who haven't been active within a VIP-tier-specific
    day range), and two "active" lists (the inverse -- active within a
    VIP-tier-specific day range). Each list is capped at the top
    ACTION_CENTER_LIST_CAP rows by relevance (closest to upgrade / most or
    least inactive) so the report and its Excel download stay a reasonable
    size."""
    rows = mconn.execute(
        "SELECT user_id, vip_level, total_recharge, user_balance, last_active_time FROM users"
    ).fetchall()

    near_low, near_high, inactive_high, inactive_low = [], [], [], []
    active_low, active_high = [], []
    for user_id, vip_level, total_recharge, user_balance, last_active_time in rows:
        if vip_level is None:
            continue
        total_recharge = total_recharge or 0.0
        inactive_days = None
        last_active_dt = parse_dt(last_active_time)
        if last_active_dt:
            inactive_days = (now - last_active_dt).days

        if vip_level < 15 and (vip_level + 1) in VIP_THRESHOLDS:
            gap = VIP_THRESHOLDS[vip_level + 1] - total_recharge
            near_row = {
                "user_id": user_id,
                "current_vip": vip_level,
                "next_vip": vip_level + 1,
                "total_deposit": round(total_recharge, 2),
                "amount_to_next": round(gap, 2),
                "inactive_days": inactive_days,
            }
            if 2 <= vip_level <= 4 and 1 <= gap <= 1000:
                near_low.append(near_row)
            elif 5 <= vip_level <= 15 and 1 <= gap <= 50000:
                near_high.append(near_row)

        if inactive_days is not None:
            inactive_row = {
                "user_id": user_id,
                "vip_level": vip_level,
                "total_deposit": round(total_recharge, 2),
                "wallet_balance": round(user_balance or 0.0, 2),
                "inactive_days": inactive_days,
                "last_active_date": last_active_dt.strftime("%Y-%m-%d") if last_active_dt else None,
            }
            if 5 <= vip_level <= 15 and 15 <= inactive_days <= 240:
                inactive_high.append(inactive_row)
            if 2 <= vip_level <= 4 and 10 <= inactive_days <= 180:
                inactive_low.append(inactive_row)

            active_row = {
                "user_id": user_id,
                "vip_level": vip_level,
                "total_deposit": round(total_recharge, 2),
                "wallet_balance": round(user_balance or 0.0, 2),
                "inactive_days": inactive_days,
            }
            if 5 <= vip_level <= 15 and inactive_days <= 15:
                active_high.append(active_row)
            if 2 <= vip_level <= 4 and inactive_days <= 10:
                active_low.append(active_row)

    near_low.sort(key=lambda r: r["amount_to_next"])
    near_high.sort(key=lambda r: r["amount_to_next"])
    inactive_high.sort(key=lambda r: -r["inactive_days"])
    inactive_low.sort(key=lambda r: -r["inactive_days"])
    active_high.sort(key=lambda r: r["inactive_days"])
    active_low.sort(key=lambda r: r["inactive_days"])

    return {
        "near_upgrade_low": {
            "note": "VIP 2 to VIP 4, gap to next level Rs 1-1000",
            "total_matching": len(near_low),
            "rows": near_low[:ACTION_CENTER_LIST_CAP],
        },
        "near_upgrade_high": {
            "note": "VIP 5 to VIP 15, gap to next level Rs 1-50000",
            "total_matching": len(near_high),
            "rows": near_high[:ACTION_CENTER_LIST_CAP],
        },
        "inactive_high": {
            "note": "VIP 5 to VIP 15, inactive 15-240 days",
            "total_matching": len(inactive_high),
            "rows": inactive_high[:ACTION_CENTER_LIST_CAP],
        },
        "inactive_low": {
            "note": "VIP 2 to VIP 4, inactive 10-180 days",
            "total_matching": len(inactive_low),
            "rows": inactive_low[:ACTION_CENTER_LIST_CAP],
        },
        "active_low": {
            "note": "VIP 2 to VIP 4, active within last 10 days",
            "total_matching": len(active_low),
            "rows": active_low[:ACTION_CENTER_LIST_CAP],
        },
        "active_high": {
            "note": "VIP 5 to VIP 15, active within last 15 days",
            "total_matching": len(active_high),
            "rows": active_high[:ACTION_CENTER_LIST_CAP],
        },
    }


def build_deposit_day_stats(deposit_rows):
    """user_id -> {date: {"count": n, "amount": total}} for COMPLETE deposits.

    NOTE: deposits are only retained for a rolling 33-day window, so a user's
    true first-ever deposit could already be purged if it happened earlier --
    in that case a later deposit here would be mis-identified as their "first
    deposit" (FD). Fine for the last-4-day FD lookback these reports use, but
    worth knowing if this function is ever reused for a longer window."""
    stats = defaultdict(lambda: defaultdict(lambda: {"count": 0, "amount": 0.0}))
    for pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit in deposit_rows:
        if status != "COMPLETE" or user_id is None:
            continue
        dt = parse_dt(create_time)
        if not dt:
            continue
        entry = stats[user_id][dt.date()]
        entry["count"] += 1
        entry["amount"] += order_amount or 0.0
    return stats


def yesterday_first_deposit_users(deposit_rows, all_withdrawal_full, vip_by_user, city_by_user, today):
    """Users flagged by the source system's own is_first_deposit column
    (column S in the water/export sheet: 0 = not first deposit, 1 = first
    deposit) as making their first-ever deposit yesterday. This is the
    authoritative flag from the platform itself, not an inference from
    deposit history -- unlike a MIN(create_time) heuristic, it isn't affected
    by the deposits table's 33-day retention window."""
    yesterday = today - timedelta(days=1)
    withdraw_by_user = defaultdict(float)
    for r in all_withdrawal_full:
        if r["status"] in ACTIVE_WITHDRAW_STATUSES and r["user_id"] is not None:
            withdraw_by_user[r["user_id"]] += r["amount"] or 0.0

    day_stats = defaultdict(lambda: {"count": 0, "amount": 0.0})
    first_deposit_users = set()
    for pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit in deposit_rows:
        if status != "COMPLETE" or user_id is None:
            continue
        dt = parse_dt(create_time)
        if not dt or dt.date() != yesterday:
            continue
        entry = day_stats[user_id]
        entry["count"] += 1
        entry["amount"] += order_amount or 0.0
        if is_first_deposit == 1:
            first_deposit_users.add(user_id)

    rows = []
    for user_id in first_deposit_users:
        entry = day_stats[user_id]
        total_deposit = round(entry["amount"], 2)
        total_withdraw = round(withdraw_by_user.get(user_id, 0.0), 2)
        rows.append({
            "user_id": user_id,
            "vip_level": vip_by_user.get(user_id),
            "deposit_count": entry["count"],
            "total_deposit": total_deposit,
            "total_withdraw": total_withdraw,
            "profit_loss": round(total_deposit - total_withdraw, 2),
            "region": city_by_user.get(user_id),
        })
    rows.sort(key=lambda r: -r["total_deposit"])
    return rows


DEPOSIT_CHALLENGE_RULES = {
    1: ("Rule 1 (+Rs10) - FD+1 Auto Bonus", 10),
    2: ("Rule 2 (+Rs20) - Deposited on FD+1", 20),
    3: ("Rule 3 (+Rs30) - Deposited on FD+2", 30),
    4: ("Rule 4 (+Rs60) - Deposited on FD+1 & FD+2", 60),
}


def deposit_challenge_bonus(deposit_day_stats, today):
    """Users whose FD falls in the last 4 days, and which of the 4 challenge
    rules they've earned so far (only rules whose award day has already
    passed are evaluated -- a rule isn't shown as "not earned" while its
    window is still open, it's just not shown yet)."""
    window_start = today - timedelta(days=3)
    rows = []
    for user_id, day_map in deposit_day_stats.items():
        fd = min(day_map.keys())
        if not (window_start <= fd <= today):
            continue
        deposited_fd1 = (fd + timedelta(days=1)) in day_map
        deposited_fd2 = (fd + timedelta(days=2)) in day_map

        def add(rule_no):
            label, amount = DEPOSIT_CHALLENGE_RULES[rule_no]
            rows.append({"user_id": user_id, "rule": label, "bonus_amount": amount, "fd_date": fd.isoformat()})

        if today >= fd + timedelta(days=1):
            add(1)
        if today >= fd + timedelta(days=2) and deposited_fd1:
            add(2)
        if today >= fd + timedelta(days=3) and deposited_fd2:
            add(3)
        if today >= fd + timedelta(days=3) and deposited_fd1 and deposited_fd2:
            add(4)

    rows.sort(key=lambda r: (r["fd_date"], r["user_id"]))
    return rows


STATUS_LABELS = {0: "In-Review", 1: "Processing", 2: "Complete", 3: "Rejected", 4: "Failed"}


def withdrawal_waiting_hours(r):
    end_dt = r["review_dt"] or r["update_dt"]
    if not r["create_dt"] or not end_dt:
        return None
    return round(max((end_dt - r["create_dt"]).total_seconds() / 3600.0, 0), 2)


def withdrawal_orders_export(withdrawal_full_records, vip_by_user):
    """Raw order-level rows for the withdrawal Excel export: order number, channel,
    amount, status, waiting time, user id and VIP level."""
    rows = []
    for r in withdrawal_full_records:
        rows.append({
            "order_no": r["order_no"],
            "channel": r["channel"],
            "amount": r["amount"],
            "status": STATUS_LABELS.get(r["status"], r["status"]),
            "waiting_hours": withdrawal_waiting_hours(r),
            "user_id": r["user_id"],
            "vip_level": vip_by_user.get(r["user_id"]),
        })
    return rows


def last4days_completion(by_date_withdrawal_full, dates):
    """For the last 4 dates: count of completed withdrawals within 4h vs more than 4h."""
    last4 = dates[-4:]
    result = []
    for date in last4:
        within, over = 0, 0
        for r in by_date_withdrawal_full.get(date, []):
            if r["status"] != 2:
                continue
            hours = withdrawal_waiting_hours(r)
            if hours is None:
                continue
            if hours <= 4:
                within += 1
            else:
                over += 1
        result.append({"date": date, "within_4h": within, "more_than_4h": over})
    return result


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    deposit_rows = cur.execute(
        "SELECT pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit FROM deposits"
    ).fetchall()
    withdrawal_rows = cur.execute(
        "SELECT withdraw_amount, create_time, status, user_id, payment_channel, review_time, update_time, order_no FROM withdrawals"
    ).fetchall()
    wallet_rows = cur.execute(
        "SELECT user_id, create_time FROM wallet_transactions WHERE user_id IS NOT NULL"
    ).fetchall()
    conn.close()

    by_date_bet_users = defaultdict(set)
    all_bet_users = set()
    for user_id, create_time in wallet_rows:
        all_bet_users.add(user_id)
        create_dt = parse_dt(create_time)
        if create_dt:
            by_date_bet_users[create_dt.strftime("%Y-%m-%d")].add(user_id)

    total_registered_users = None
    vip_by_user = {}
    city_by_user = {}
    action_center = None
    # Source timestamps (create_time, last_active_time, etc.) are IST, but this
    # script runs on a UTC-clocked GitHub Actions runner -- datetime.now() would
    # be ~5.5h behind IST, making very recent activity look like it's in the
    # future (negative inactive_days/hours). Compute "now" in IST to match.
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    master_db_path = os.path.join(BASE, "master_userlist.db")
    if os.path.exists(master_db_path):
        mconn = sqlite3.connect(master_db_path)
        total_registered_users = mconn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        vip_by_user = dict(mconn.execute("SELECT user_id, vip_level FROM users").fetchall())
        city_by_user = dict(mconn.execute("SELECT user_id, city FROM users").fetchall())
        action_center = action_center_reports(mconn, now)
        mconn.close()

    by_date_records = defaultdict(list)
    all_records = []
    by_date_withdrawals = defaultdict(list)
    all_withdrawals = []
    latest_record_time = None

    for pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit in deposit_rows:
        channel = pay_channel or "Unknown"
        amount = order_amount or 0.0
        date_str, hour = None, None
        create_dt = parse_dt(create_time)
        if create_dt:
            date_str, hour = create_dt.strftime("%Y-%m-%d"), create_dt.hour
            if latest_record_time is None or create_dt > latest_record_time:
                latest_record_time = create_dt

        completion_minutes = None
        if status == "COMPLETE":
            update_dt = parse_dt(update_time)
            if create_dt and update_dt:
                completion_minutes = max((update_dt - create_dt).total_seconds() / 60.0, 0)

        record = {
            "channel": channel,
            "amount": amount,
            "hour": hour,
            "status": status,
            "completion_minutes": completion_minutes,
            "user_id": user_id,
        }
        all_records.append(record)
        if date_str:
            by_date_records[date_str].append(record)

    by_date_withdrawal_full = defaultdict(list)
    all_withdrawal_full = []

    for withdraw_amount, create_time, status, user_id, payment_channel, review_time, update_time, order_no in withdrawal_rows:
        amount = withdraw_amount or 0.0
        create_dt = parse_dt(create_time)
        date_str = create_dt.strftime("%Y-%m-%d") if create_dt else None
        if create_dt and (latest_record_time is None or create_dt > latest_record_time):
            latest_record_time = create_dt
        record = {"amount": amount, "status": status, "user_id": user_id}
        all_withdrawals.append(record)
        if date_str:
            by_date_withdrawals[date_str].append(record)

        full_record = {
            "channel": payment_channel or "Unknown",
            "status": status,
            "create_dt": create_dt,
            "review_dt": parse_dt(review_time),
            "update_dt": parse_dt(update_time),
            "order_no": order_no,
            "user_id": user_id,
            "amount": amount,
        }
        all_withdrawal_full.append(full_record)
        if date_str:
            by_date_withdrawal_full[date_str].append(full_record)

    all_dates = sorted(set(by_date_records.keys()) | set(by_date_withdrawals.keys()))
    by_date = {
        date: {
            **aggregate(by_date_records.get(date, [])),
            "summary": summarize(
                by_date_records.get(date, []), by_date_withdrawals.get(date, []), by_date_bet_users.get(date, set())
            ),
            "withdrawal_review_by_channel": withdrawal_review_by_channel(by_date_withdrawal_full.get(date, [])),
            "withdrawal_completion_by_channel": withdrawal_completion_by_channel(by_date_withdrawal_full.get(date, [])),
            "withdrawal_orders": withdrawal_orders_export(by_date_withdrawal_full.get(date, []), vip_by_user),
        }
        for date in all_dates
    }

    withdrawal_analysis = {
        "processing_time_buckets": PROCESSING_TIME_BUCKETS,
        "processing_backlog_buckets": PROCESSING_BACKLOG_BUCKETS,
        "inreview_backlog_buckets": INREVIEW_BACKLOG_BUCKETS,
        "processing_backlog": withdrawal_backlog(all_withdrawal_full, now, 1, processing_backlog_bucket, PROCESSING_BACKLOG_BUCKETS),
        "inreview_backlog": withdrawal_backlog(all_withdrawal_full, now, 0, inreview_backlog_bucket, INREVIEW_BACKLOG_BUCKETS),
        "backlog_as_of": now.isoformat(),
        "last4days_completion": last4days_completion(by_date_withdrawal_full, all_dates),
    }

    action_center_extra = {
        "yesterday_first_deposit_users": yesterday_first_deposit_users(deposit_rows, all_withdrawal_full, vip_by_user, city_by_user, now.date()),
        "deposit_challenge_bonus": deposit_challenge_bonus(build_deposit_day_stats(deposit_rows), now.date()),
    }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_record_time": latest_record_time.isoformat() if latest_record_time else None,
        "total_registered_users": total_registered_users,
        "status_filter": "COMPLETE (success-rate sections include all statuses)",
        "amount_ranges": RANGE_LABELS[:-1],
        "dates": all_dates,
        "by_date": by_date,
        "all_time": {
            **aggregate(all_records),
            "summary": summarize(all_records, all_withdrawals, all_bet_users),
            "withdrawal_review_by_channel": withdrawal_review_by_channel(all_withdrawal_full),
            "withdrawal_completion_by_channel": withdrawal_completion_by_channel(all_withdrawal_full),
        },
        "withdrawal_analysis": withdrawal_analysis,
        "action_center": action_center,
        "action_center_extra": action_center_extra,
    }

    out_path = os.path.join(BASE, "deposit_report.json")
    with open(out_path, "w") as f:
        json.dump(report, f)
    completed_n = sum(1 for r in all_records if r["status"] == "COMPLETE")
    print(f"Wrote {out_path} ({completed_n}/{len(all_records)} completed deposits across {len(by_date)} dates)")

    creds = load_creds()
    s3 = boto3.client(
        "s3",
        endpoint_url=creds["R2_ENDPOINT_URL"],
        aws_access_key_id=creds["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=creds["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    s3.upload_file(out_path, creds["R2_BUCKET"], "reports/deposit_report.json")
    print(f"Uploaded reports/deposit_report.json -> r2://{creds['R2_BUCKET']}/reports/deposit_report.json")


if __name__ == "__main__":
    main()
