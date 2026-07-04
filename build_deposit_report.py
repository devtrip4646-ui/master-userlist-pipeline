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
from datetime import time as dtime

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


def load_json_with_r2_fallback(local_path, r2_key, creds, default):
    """Load a local JSON artifact if present (handed off same-job from
    api_pull_ingest.py), otherwise fall back to the copy it also uploads to
    R2. Needed because ingest.yml -- dispatched by ANY dashboard file
    upload (userlist/deposits/withdrawals/wallet/agents/bulk_reassign), not
    just the hourly api_pull.yml job -- re-runs this script in its OWN
    fresh checkout, with no local copy of reactivation/vip_upgrade
    candidates from the last api_pull.yml run. Without this fallback,
    Reactivation/VIP Upgrade silently zero out on every such upload until
    the next hourly run overwrites them again."""
    if os.path.exists(local_path):
        with open(local_path) as f:
            return json.load(f)
    try:
        s3 = boto3.client(
            "s3",
            endpoint_url=creds["R2_ENDPOINT_URL"],
            aws_access_key_id=creds["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=creds["R2_SECRET_ACCESS_KEY"],
            region_name="auto",
        )
        s3.download_file(creds["R2_BUCKET"], r2_key, local_path)
        with open(local_path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Could not load {r2_key} from R2 (falling back to empty): {e}")
        return default


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

AGENT_UNASSIGNED = "Un-Assigned"


def agent_for(agent_by_user, user_id):
    return agent_by_user.get(user_id) or AGENT_UNASSIGNED


def tally_by_agent(user_ids, agent_by_user):
    """{agent_name: count} for a collection of user_ids -- used for the
    Performance page's per-agent cohort/target denominators, which need the
    TRUE uncapped count, not the ACTION_CENTER_LIST_CAP-limited `rows` list
    used for on-screen display."""
    counts = defaultdict(int)
    for uid in user_ids:
        counts[agent_for(agent_by_user, uid)] += 1
    return dict(counts)


def tally_rows_by_agent(rows):
    """Same as tally_by_agent, but for a list of row dicts that already carry
    an "agent" key (cheaper than re-deriving it from user_id)."""
    counts = defaultdict(int)
    for r in rows:
        counts[r["agent"]] += 1
    return dict(counts)


def action_center_reports(mconn, now, agent_by_user):
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
                "agent": agent_for(agent_by_user, user_id),
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
                "agent": agent_for(agent_by_user, user_id),
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
                "agent": agent_for(agent_by_user, user_id),
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


def deposit_reactivation_analytics(mconn, reactivation_candidates, action_center, agent_by_user):
    """Users active TODAY (deposit, withdrawal, or wallet/bet activity --
    whichever is most recent) after a qualifying inactive gap since their
    previous activity. Two VIP-tier-scoped cohorts, using the same day ranges
    as the Inactive-Low/Inactive-High action-center lists so a user "moving"
    from one report to the other is exactly consistent:
      Low  (VIP2-4):  previous gap 10-180 days
      High (VIP5-15): previous gap 15-240 days
    total_deposit on each row is specifically today's DEPOSIT amount (0 if
    the user reactivated via a withdrawal or wallet transaction with no
    matching deposit today) -- VIP/total_recharge stay deposit-only even
    though the activity/inactivity signal itself is not.

    reactivation_candidates comes from api_pull_ingest.py's
    sync_master_userlist(), NOT derived here from daily_records.db directly
    -- those tables are purged to a rolling 33-day window, which would
    silently drop every comeback after a longer gap (i.e. most of the
    10-180/15-240 day range). sync_master_userlist runs earlier in the same
    job and is the only place that still has each user's PRE-update
    last_active_time (unbounded history), so it computes the true gap there
    and hands the candidate list off via a local JSON file.

    "% reactivated" denominator is reconstructed as reactivated_today +
    still_currently_inactive (from action_center, already computed this run
    -- reactivated users are correctly excluded from it since their
    inactive_days reset to 0 once today's activity lands in master_userlist.db).
    No separate "yesterday's inactive list" snapshot needs to be stored."""
    vip_by_user = dict(mconn.execute("SELECT user_id, vip_level FROM users").fetchall())

    low_rows, high_rows = [], []
    for cand in reactivation_candidates:
        user_id = cand["user_id"]
        gap_days = cand["inactive_days"]
        vip_level = vip_by_user.get(user_id)
        if vip_level is None:
            continue
        row = {
            "user_id": user_id,
            "agent": agent_for(agent_by_user, user_id),
            "vip_level": vip_level,
            "total_deposit": cand["total_deposit"],
            "inactive_days": gap_days,
        }
        if 2 <= vip_level <= 4 and 10 <= gap_days <= 180:
            low_rows.append(row)
        elif 5 <= vip_level <= 15 and 15 <= gap_days <= 240:
            high_rows.append(row)

    low_rows.sort(key=lambda r: -r["inactive_days"])
    high_rows.sort(key=lambda r: -r["inactive_days"])

    still_inactive_low = action_center["inactive_low"]["total_matching"] if action_center else 0
    still_inactive_high = action_center["inactive_high"]["total_matching"] if action_center else 0
    baseline_low = len(low_rows) + still_inactive_low
    baseline_high = len(high_rows) + still_inactive_high

    return {
        "low": {
            "note": "VIP 2 to VIP 4, reactivated today (was inactive 10-180 days)",
            "reactivated_count": len(low_rows),
            "pct_reactivated": round(len(low_rows) / baseline_low * 100, 2) if baseline_low else 0.0,
            # Per-agent count of reactivated users, from the FULL (uncapped)
            # low_rows list -- feeds the Performance page's Reactivation Low
            # criterion (target: 7/day), which needs the true count even
            # when the on-screen `rows` list is capped for display size.
            "agent_breakdown": tally_rows_by_agent(low_rows),
            "rows": low_rows[:ACTION_CENTER_LIST_CAP],
        },
        "high": {
            "note": "VIP 5 to VIP 15, reactivated today (was inactive 15-240 days)",
            "reactivated_count": len(high_rows),
            "pct_reactivated": round(len(high_rows) / baseline_high * 100, 2) if baseline_high else 0.0,
            "agent_breakdown": tally_rows_by_agent(high_rows),
            "rows": high_rows[:ACTION_CENTER_LIST_CAP],
        },
    }


def vip_upgrade_analytics(vip_upgrade_candidates, action_center, agent_by_user):
    """Users who were in the near-upgrade cohort (gap Rs 1-1000 for VIP2-4,
    Rs 1-50000 for VIP5-15) as of the START of today and have since crossed
    into the next VIP tier. vip_upgrade_candidates comes from
    api_pull_ingest.py's sync_master_userlist(), which is the only place
    with a stable day-start snapshot to compare against (the pipeline runs
    hourly, so a naive "before this run vs after this run" diff would lose
    upgrades from earlier the same day once a later run's report overwrites
    it).

    Each row also carries amount_over_minimum = today's deposit minus the
    exact gap that was needed to cross the threshold -- a bare-minimum
    crosser is ~0, a big spender well above it. Useful for telling "the
    near-upgrade push is converting people right at the line" apart from
    "these are just big depositors who would have crossed anyway".

    "% converted" denominator is reconstructed as upgraded_today +
    still_near_upgrade (from action_center's near_upgrade_low/high, already
    computed this run), same pattern as the Reactivation report."""
    low_rows = sorted(vip_upgrade_candidates.get("low", []), key=lambda r: -r["total_deposit"])
    high_rows = sorted(vip_upgrade_candidates.get("high", []), key=lambda r: -r["total_deposit"])
    for r in low_rows + high_rows:
        r["agent"] = agent_for(agent_by_user, r["user_id"])

    still_near_low = action_center["near_upgrade_low"]["total_matching"] if action_center else 0
    still_near_high = action_center["near_upgrade_high"]["total_matching"] if action_center else 0
    baseline_low = len(low_rows) + still_near_low
    baseline_high = len(high_rows) + still_near_high

    return {
        "low": {
            "note": "VIP 2 to VIP 4, upgraded today from the near-upgrade cohort",
            "upgraded_count": len(low_rows),
            "pct_upgraded": round(len(low_rows) / baseline_low * 100, 2) if baseline_low else 0.0,
            "agent_breakdown": tally_rows_by_agent(low_rows),
            "rows": low_rows[:ACTION_CENTER_LIST_CAP],
        },
        "high": {
            "note": "VIP 5 to VIP 15, upgraded today from the near-upgrade cohort",
            "upgraded_count": len(high_rows),
            "pct_upgraded": round(len(high_rows) / baseline_high * 100, 2) if baseline_high else 0.0,
            "agent_breakdown": tally_rows_by_agent(high_rows),
            "rows": high_rows[:ACTION_CENTER_LIST_CAP],
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


def yesterday_first_deposit_users(deposit_rows, all_withdrawal_full, vip_by_user, city_by_user, today, agent_by_user):
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
            "agent": agent_for(agent_by_user, user_id),
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


def deposit_challenge_bonus(deposit_rows, deposit_day_stats, today, agent_by_user):
    """Bonuses payable TODAY only -- a daily payout worksheet, not a rolling
    history of everything earned in the last few days. Each rule has a fixed
    FD offset that determines which FD cohort is relevant for today's payout:
      Rule 1 (+Rs10, auto):                  FD = today - 1
      Rule 2 (+Rs20, if deposited on FD+1):  FD = today - 2
      Rule 3 (+Rs30, if deposited on FD+2):  FD = today - 3
      Rule 4 (+Rs60, if deposited FD+1&+2):  FD = today - 3
    FD is taken from the source system's own is_first_deposit column (column S
    in the water/export sheet: 1 = first deposit), not inferred from
    MIN(create_time) -- the flag is authoritative and isn't affected by the
    deposits table's 33-day retention window."""
    fd_by_user = {}
    for pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit in deposit_rows:
        if status != "COMPLETE" or user_id is None or is_first_deposit != 1:
            continue
        dt = parse_dt(create_time)
        if not dt:
            continue
        fd_by_user[user_id] = dt.date()

    rows = []
    for user_id, fd in fd_by_user.items():
        day_map = deposit_day_stats.get(user_id, {})
        deposited_fd1 = (fd + timedelta(days=1)) in day_map
        deposited_fd2 = (fd + timedelta(days=2)) in day_map

        def add(rule_no):
            label, amount = DEPOSIT_CHALLENGE_RULES[rule_no]
            rows.append({
                "user_id": user_id, "agent": agent_for(agent_by_user, user_id), "rule": label,
                "bonus_amount": amount, "fd_date": fd.isoformat(),
            })

        if fd == today - timedelta(days=1):
            add(1)
        if fd == today - timedelta(days=2) and deposited_fd1:
            add(2)
        if fd == today - timedelta(days=3):
            if deposited_fd2:
                add(3)
            if deposited_fd1 and deposited_fd2:
                add(4)

    # Highest bonus first -- surfaces the more meaningful Rule 2/3/4 winners
    # (users who actually kept depositing) ahead of the many Rule 1 auto-awards.
    rows.sort(key=lambda r: (-r["bonus_amount"], r["user_id"]))
    return rows


def _today_deposit_activity(deposit_rows, today):
    """user_id -> {"count", "amount"} for COMPLETE deposits dated TODAY.
    Shared by both retention reports below."""
    activity = defaultdict(lambda: {"count": 0, "amount": 0.0})
    for pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit in deposit_rows:
        if status != "COMPLETE" or user_id is None:
            continue
        dt = parse_dt(create_time)
        if not dt or dt.date() != today:
            continue
        entry = activity[user_id]
        entry["count"] += 1
        entry["amount"] += order_amount or 0.0
    return activity


def _retention_report(cohort, today_activity, city_by_user, note, agent_by_user):
    """Shared shape for both retention reports: cohort_size, converted_count,
    pct_converted, avg_deposit_amount (of converters -- a headcount-only
    conversion rate treats a Rs200 top-up and a Rs20,000 deposit as
    identical; this flags whether the retained users are actually
    meaningful deposits or just token amounts to stay counted), and the
    per-user row list."""
    rows = []
    for user_id in cohort:
        activity = today_activity.get(user_id)
        if not activity:
            continue
        rows.append({
            "user_id": user_id,
            "agent": agent_for(agent_by_user, user_id),
            "total_deposit": round(activity["amount"], 2),
            "deposit_count": activity["count"],
            "region": city_by_user.get(user_id) or "Unknown",
        })
    rows.sort(key=lambda r: -r["total_deposit"])
    cohort_size = len(cohort)
    converted = len(rows)
    avg_deposit = round(sum(r["total_deposit"] for r in rows) / converted, 2) if converted else 0.0
    return {
        "note": note,
        "cohort_size": cohort_size,
        "converted_count": converted,
        "pct_converted": round(converted / cohort_size * 100, 2) if cohort_size else 0.0,
        "avg_deposit_amount": avg_deposit,
        # Per-agent cohort/converted counts (full, uncapped) -- feeds the
        # Performance page's Retention criterion (target: 30%), computed
        # from First-Deposit retention specifically (see first_deposit_retention).
        "cohort_by_agent": tally_by_agent(cohort, agent_by_user),
        "converted_by_agent": tally_rows_by_agent(rows),
        "rows": rows[:ACTION_CENTER_LIST_CAP],
    }


def first_deposit_retention(deposit_rows, city_by_user, today, agent_by_user):
    """Of users whose first-ever deposit (the source system's own
    is_first_deposit flag) was YESTERDAY, how many made another COMPLETE
    deposit TODAY -- a basic Day-1 retention signal. Computed directly from
    deposit_rows (not a day-start snapshot, unlike Reactivation/VIP Upgrade)
    since "yesterday" and "today" are both fully derivable from timestamps
    already sitting in every row, so it's naturally correct regardless of
    which hourly run computes it."""
    yesterday = today - timedelta(days=1)
    fd_yesterday = set()
    for pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit in deposit_rows:
        if status != "COMPLETE" or user_id is None or is_first_deposit != 1:
            continue
        dt = parse_dt(create_time)
        if dt and dt.date() == yesterday:
            fd_yesterday.add(user_id)
    return _retention_report(
        fd_yesterday, _today_deposit_activity(deposit_rows, today), city_by_user,
        "Yesterday's first-deposit users who deposited again today", agent_by_user,
    )


def bonus_claimer_retention(bonus_rows, deposit_rows, city_by_user, today, agent_by_user):
    """Of users who claimed the 3-Day Deposit Challenge Bonus's Rule 3
    (+Rs30, deposited FD+2) or Rule 4 (+Rs60, deposited FD+1 and FD+2) TODAY,
    how many ALSO made a COMPLETE deposit TODAY. The bonus-qualifying
    deposits are from FD+1/FD+2 (1-2 days ago), never today, so this is a
    genuinely separate signal -- not circular with the bonus itself: are the
    bigger-bonus earners still actively depositing, or was claiming the
    bonus their last action?"""
    claimers = {r["user_id"] for r in bonus_rows if r["bonus_amount"] in (30, 60)}
    return _retention_report(
        claimers, _today_deposit_activity(deposit_rows, today), city_by_user,
        "Rule 3 (Rs30) / Rule 4 (Rs60) bonus claimers today who deposited again today", agent_by_user,
    )


def premium_active_conversion(mconn, deposit_rows, now, agent_by_user):
    """Of users already on the Active Users list in Action Center (VIP2-4
    active within 10 days = "low", VIP5-15 active within 15 days = "high"),
    how many ALSO made a COMPLETE deposit specifically TODAY -- a continued-
    engagement signal, distinct from Reactivation (which tracks INACTIVE
    users coming back) and from Active Users itself (which only shows who's
    active, not who's converting today).

    Recomputes the full active_low/active_high user_id membership directly
    (duplicating action_center_reports' classification, not reusing its
    output) because that report caps its `rows` at ACTION_CENTER_LIST_CAP
    for display size -- an accurate conversion % here needs the TRUE
    cohort size, not a capped subset."""
    rows = mconn.execute("SELECT user_id, vip_level, last_active_time FROM users").fetchall()
    active_low_ids, active_high_ids = set(), set()
    vip_by_user = {}
    for user_id, vip_level, last_active_time in rows:
        if vip_level is None:
            continue
        vip_by_user[user_id] = vip_level
        last_active_dt = parse_dt(last_active_time)
        if not last_active_dt:
            continue
        inactive_days = (now - last_active_dt).days
        if 2 <= vip_level <= 4 and inactive_days <= 10:
            active_low_ids.add(user_id)
        if 5 <= vip_level <= 15 and inactive_days <= 15:
            active_high_ids.add(user_id)

    today_activity = _today_deposit_activity(deposit_rows, now.date())

    def build(cohort, tier_label):
        rows_out = []
        for user_id in cohort:
            activity = today_activity.get(user_id)
            if not activity:
                continue
            rows_out.append({
                "user_id": user_id,
                "agent": agent_for(agent_by_user, user_id),
                "vip": vip_by_user.get(user_id),
                "deposit_amount": round(activity["amount"], 2),
                "deposit_count": activity["count"],
            })
        rows_out.sort(key=lambda r: -r["deposit_amount"])
        cohort_size = len(cohort)
        converted = len(rows_out)
        avg_deposit = round(sum(r["deposit_amount"] for r in rows_out) / converted, 2) if converted else 0.0
        return {
            "note": f"{tier_label} Active Users who deposited today",
            "cohort_size": cohort_size,
            "converted_count": converted,
            "pct_converted": round(converted / cohort_size * 100, 2) if cohort_size else 0.0,
            "avg_deposit_amount": avg_deposit,
            # Per-agent cohort/converted counts (full, uncapped) -- feeds the
            # Performance page's Low/High Premium Active criteria (targets:
            # 35%/30% of the agent's own active-user cohort).
            "cohort_by_agent": tally_by_agent(cohort, agent_by_user),
            "converted_by_agent": tally_rows_by_agent(rows_out),
            "rows": rows_out[:ACTION_CENTER_LIST_CAP],
        }

    return {"low": build(active_low_ids, "Low"), "high": build(active_high_ids, "High")}


STATUS_LABELS = {0: "In-Review", 1: "Processing", 2: "Complete", 3: "Rejected", 4: "Failed"}


def withdrawal_waiting_hours(r):
    end_dt = r["review_dt"] or r["update_dt"]
    if not r["create_dt"] or not end_dt:
        return None
    return round(max((end_dt - r["create_dt"]).total_seconds() / 3600.0, 0), 2)


def withdrawal_orders_export(withdrawal_full_records, vip_by_user, now, agent_by_user):
    """Raw order-level rows for the withdrawal Excel export: order number
    (both order_no and payment_center_order_no -- the latter is the
    "TW..."-prefixed field, the closest match found to a requested
    "TP"-prefixed order number; order_no itself is "DIZC..."-prefixed and
    channel_order_id is inconsistent, neither matches), channel, amount,
    status, date, waiting time, user id and VIP level. For orders still open
    (status 0 In-Review / 1 Processing), also computes hours_in_review /
    hours_processing as (now - create_time) -- how long the order has actually
    been sitting in that state as of report generation. waiting_hours (which
    uses review_time/update_time) is near-zero for these still-open orders
    since they haven't been reviewed/updated yet, so it can't answer "how long
    has this been pending" -- these two fields exist specifically for that."""
    rows = []
    for r in withdrawal_full_records:
        hours_in_review = hours_processing = None
        if r["status"] in (0, 1) and r["create_dt"]:
            pending_hours = round(max((now - r["create_dt"]).total_seconds() / 3600.0, 0), 2)
            if r["status"] == 0:
                hours_in_review = pending_hours
            else:
                hours_processing = pending_hours
        rows.append({
            "order_no": r["order_no"],
            "payment_center_order_no": r.get("payment_center_order_id"),
            "channel": r["channel"],
            "amount": r["amount"],
            "status": STATUS_LABELS.get(r["status"], r["status"]),
            "date": r["create_dt"].strftime("%Y-%m-%d") if r["create_dt"] else None,
            "waiting_hours": withdrawal_waiting_hours(r),
            "hours_in_review": hours_in_review,
            "hours_processing": hours_processing,
            "user_id": r["user_id"],
            "agent": agent_for(agent_by_user, r["user_id"]),
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


def region_vip_deposit_analytics(by_date_records, by_date_withdrawals, city_by_user, vip_by_user, dates):
    """For each of the last 7 dates: top 10 regions by total COMPLETE deposit
    amount (with order count, unique user count, total withdrawal, and net
    revenue = deposit - withdrawal), and the same breakdown per VIP level.
    Powers the Analytics page's region/VIP charts with a 7-day date switch.

    Net revenue matters here because gross deposit volume alone can be
    misleading -- a region can look like a top performer by deposit total
    while actually being net-negative for the house once withdrawals are
    subtracted. Regions/tiers are still ranked by deposit (that's still the
    natural "where's the volume" question), but every row also carries
    total_withdrawal/net_revenue so that's never hidden."""
    last7 = dates[-7:]
    result = {}
    for date in last7:
        region_totals = defaultdict(float)
        region_counts = defaultdict(int)
        region_users = defaultdict(set)
        region_withdrawals = defaultdict(float)
        vip_totals = defaultdict(float)
        vip_counts = defaultdict(int)
        vip_users = defaultdict(set)
        vip_withdrawals = defaultdict(float)
        for r in by_date_records.get(date, []):
            if r["status"] != "COMPLETE" or r["user_id"] is None:
                continue
            region = city_by_user.get(r["user_id"]) or "Unknown"
            region_totals[region] += r["amount"]
            region_counts[region] += 1
            region_users[region].add(r["user_id"])
            vip = vip_by_user.get(r["user_id"])
            if vip is not None:
                vip_totals[vip] += r["amount"]
                vip_counts[vip] += 1
                vip_users[vip].add(r["user_id"])
        for r in by_date_withdrawals.get(date, []):
            if r["status"] != 2 or r["user_id"] is None:  # 2 = Complete
                continue
            region = city_by_user.get(r["user_id"]) or "Unknown"
            region_withdrawals[region] += r["amount"]
            vip = vip_by_user.get(r["user_id"])
            if vip is not None:
                vip_withdrawals[vip] += r["amount"]
        top_regions = sorted(region_totals.items(), key=lambda x: -x[1])[:10]
        vip_rows = [
            {
                "vip_level": vip,
                "total_deposit": round(vip_totals[vip], 2),
                "count": vip_counts[vip],
                "user_count": len(vip_users[vip]),
                "total_withdrawal": round(vip_withdrawals.get(vip, 0.0), 2),
                "net_revenue": round(vip_totals[vip] - vip_withdrawals.get(vip, 0.0), 2),
            }
            for vip in sorted(vip_totals.keys())
        ]
        result[date] = {
            "top_regions": [
                {
                    "region": region,
                    "total_deposit": round(total, 2),
                    "count": region_counts[region],
                    "user_count": len(region_users[region]),
                    "total_withdrawal": round(region_withdrawals.get(region, 0.0), 2),
                    "net_revenue": round(total - region_withdrawals.get(region, 0.0), 2),
                }
                for region, total in top_regions
            ],
            "vip_breakdown": vip_rows,
        }
    return result


def performance_history(mconn):
    """Permanent daily/weekly/monthly Total Deposit / Total Withdrawal / Net
    Revenue trends. Reads from master_userlist.db's daily_performance table
    (populated once per day by api_pull_ingest.py's sync_master_userlist),
    which is NEVER purged -- unlike daily_records.db's rolling 33-day
    window, this is unlimited history: every day's totals survive forever
    once written, even after that day's row-level detail eventually ages
    out and gets purged. Weekly/monthly are derived here on read via simple
    date-bucketing since daily_performance itself stays small (one row per
    calendar date, not per transaction)."""
    try:
        daily_rows = mconn.execute(
            "SELECT date, total_deposit, deposit_count, unique_depositors, "
            "total_withdrawal, withdrawal_count, unique_withdrawers, net_revenue "
            "FROM daily_performance ORDER BY date"
        ).fetchall()
    except sqlite3.OperationalError:
        return {"daily": [], "weekly": [], "monthly": []}  # pre-dates this feature

    daily = [
        {
            "date": d, "total_deposit": td, "deposit_count": dc, "unique_depositors": ud,
            "total_withdrawal": tw, "withdrawal_count": wc, "unique_withdrawers": uw, "net_revenue": nr,
        }
        for d, td, dc, ud, tw, wc, uw, nr in daily_rows
    ]

    def rollup(rows, key_fn):
        buckets = {}
        for r in rows:
            key = key_fn(r["date"])
            b = buckets.setdefault(key, {
                "period": key, "start_date": r["date"], "end_date": r["date"],
                "total_deposit": 0.0, "total_withdrawal": 0.0, "net_revenue": 0.0,
                "deposit_count": 0, "withdrawal_count": 0,
            })
            b["total_deposit"] += r["total_deposit"]
            b["total_withdrawal"] += r["total_withdrawal"]
            b["net_revenue"] += r["net_revenue"]
            b["deposit_count"] += r["deposit_count"]
            b["withdrawal_count"] += r["withdrawal_count"]
            b["start_date"] = min(b["start_date"], r["date"])
            b["end_date"] = max(b["end_date"], r["date"])
        result = sorted(buckets.values(), key=lambda b: b["start_date"])
        for b in result:
            b["total_deposit"] = round(b["total_deposit"], 2)
            b["total_withdrawal"] = round(b["total_withdrawal"], 2)
            b["net_revenue"] = round(b["net_revenue"], 2)
        return result

    def week_key(date_str):
        y, w, _ = datetime.strptime(date_str, "%Y-%m-%d").isocalendar()
        return f"{y}-W{w:02d}"

    def month_key(date_str):
        return date_str[:7]

    return {
        "daily": daily,
        "weekly": rollup(daily, week_key),
        "monthly": rollup(daily, month_key),
    }


def profit_users_of_the_day(mconn, deposit_rows, withdrawal_rows, now, agent_by_user):
    """Top users by CURRENT wallet balance (user_balance on
    master_userlist.db, continuously updated by wallet activity) -- "who is
    sitting on the most money right now", enriched with today's deposit/
    withdrawal activity and permanent last-deposit/last-withdrawal dates.

    Last deposit/withdraw use deposit_sync_time/withdrawal_sync_time (see
    sync_master_userlist in api_pull_ingest.py) rather than deriving from
    daily_records.db's deposit_rows/withdrawal_rows directly -- those are
    purged to a rolling 33-day window, so a user who hasn't deposited in
    longer than that would wrongly show "no deposit" instead of their true
    last date. deposit_sync_time/withdrawal_sync_time are permanent,
    continuously advanced every run, and immune to that purge."""
    today = now.date()
    today_deposit = defaultdict(float)
    for pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit in deposit_rows:
        if status != "COMPLETE" or user_id is None:
            continue
        dt = parse_dt(create_time)
        if dt and dt.date() == today:
            today_deposit[user_id] += order_amount or 0.0

    today_withdraw = defaultdict(float)
    for withdraw_amount, create_time, status, user_id, payment_channel, review_time, update_time, order_no, payment_center_order_id in withdrawal_rows:
        if status != 2 or user_id is None:  # 2 = Complete
            continue
        dt = parse_dt(create_time)
        if dt and dt.date() == today:
            today_withdraw[user_id] += withdraw_amount or 0.0

    def days_ago_label(sync_time):
        dt = parse_dt(sync_time)
        if not dt:
            return None
        gap = (today - dt.date()).days
        return "Today" if gap <= 0 else f"{gap}d ago"

    rows = mconn.execute(
        "SELECT user_id, vip_level, user_balance, deposit_sync_time, withdrawal_sync_time FROM users "
        "WHERE user_balance IS NOT NULL AND user_balance > 0 "
        "ORDER BY user_balance DESC LIMIT ?",
        (ACTION_CENTER_LIST_CAP,),
    ).fetchall()

    result = []
    for user_id, vip_level, user_balance, dep_sync, wd_sync in rows:
        dep_today = round(today_deposit.get(user_id, 0.0), 2)
        wd_today = round(today_withdraw.get(user_id, 0.0), 2)
        result.append({
            "user_id": user_id,
            "agent": agent_for(agent_by_user, user_id),
            "vip": vip_level,
            "dep_today": dep_today,
            "wallet_bal": round(user_balance or 0.0, 2),
            "wd_today": wd_today,
            "net_dep": round(dep_today - wd_today, 2),
            "last_dep": days_ago_label(dep_sync),
            "last_wd": days_ago_label(wd_sync),
        })
    return result


def channel_performance_report(daily_conn, today):
    """Channel acquisition quality, last 4 days combined. Of users whose
    FIRST deposit (is_first_deposit=1) landed in the last 4 calendar days,
    grouped by acquisition channel (deposits' own 'channel' column,
    spreadsheet column P -- the marketing/agent referral channel, not
    pay_channel/payment method): FD Users, FD Amount, Avg FD, and how many
    came back to deposit again on Day 2 (FD+1) and Day 3 (FD+2).

    Quality is a simple heuristic: a high average first-deposit amount
    marks a valuable acquisition regardless of short-term return rate
    ("High value"); otherwise it's graded on Day-2 return rate (Good >=25%,
    Average 15-24%, Weak <15%)."""
    window_start = today - timedelta(days=3)
    rows = daily_conn.execute(
        "SELECT channel, user_id, order_amount, create_time, is_first_deposit FROM deposits "
        "WHERE status = 'COMPLETE' AND create_time >= ?",
        (window_start.isoformat(),),
    ).fetchall()

    fd_by_user = {}
    deposit_dates_by_user = defaultdict(set)
    for channel, user_id, order_amount, create_time, is_first_deposit in rows:
        if user_id is None:
            continue
        dt = parse_dt(create_time)
        if not dt:
            continue
        deposit_dates_by_user[user_id].add(dt.date())
        if is_first_deposit == 1 and dt.date() >= window_start:
            fd_by_user[user_id] = (channel or "Unknown", dt.date(), order_amount or 0.0)

    by_channel = defaultdict(lambda: {"fd_users": 0, "fd_amount": 0.0, "d2_users": 0, "d3_users": 0})
    for user_id, (channel, fd_date, fd_amount) in fd_by_user.items():
        b = by_channel[channel]
        b["fd_users"] += 1
        b["fd_amount"] += fd_amount
        day_map = deposit_dates_by_user.get(user_id, set())
        if (fd_date + timedelta(days=1)) in day_map:
            b["d2_users"] += 1
        if (fd_date + timedelta(days=2)) in day_map:
            b["d3_users"] += 1

    def quality(avg_fd, d2_pct):
        if avg_fd >= 800:
            return "High value"
        if d2_pct >= 25:
            return "Good"
        if d2_pct >= 15:
            return "Average"
        return "Weak"

    result = []
    for channel, b in by_channel.items():
        avg_fd = round(b["fd_amount"] / b["fd_users"], 2) if b["fd_users"] else 0.0
        d2_pct = round(b["d2_users"] / b["fd_users"] * 100, 1) if b["fd_users"] else 0.0
        d3_pct = round(b["d3_users"] / b["fd_users"] * 100, 1) if b["fd_users"] else 0.0
        result.append({
            "channel": channel,
            "fd_users": b["fd_users"],
            "fd_amount": round(b["fd_amount"], 2),
            "avg_fd": avg_fd,
            "d2_users": b["d2_users"],
            "d2_pct": d2_pct,
            "d3_users": b["d3_users"],
            "d3_pct": d3_pct,
            "quality": quality(avg_fd, d2_pct),
        })
    result.sort(key=lambda r: -r["fd_users"])
    return result


USER_SEARCH_SHARDS = 40


def build_recent_activity_by_user(daily_conn, today):
    """The daily_records.db-dependent half of the user search index: recent
    deposits (7 days, with order_no -- not in the shared deposit_rows tuple
    used everywhere else, so this is a dedicated query), recent withdrawals
    (7 days), and recent games played (2 days, excluding bonus payouts via
    `id NOT IN (SELECT id FROM bonuses)` -- bonuses.id directly reuses the
    source wallet_transactions.id, see ingest_wallet() in ingest_update.py,
    so this is an exact join, not a name-matching heuristic repeated a third
    time). Called while `conn` is still open, same as channel_performance_report,
    since daily_records.db's connection is closed early in main()."""
    dep_start = (today - timedelta(days=6)).isoformat()
    deposits_by_user = defaultdict(list)
    for user_id, order_amount, create_time, status, order_no, pay_channel in daily_conn.execute(
        "SELECT user_id, order_amount, create_time, status, order_no, pay_channel FROM deposits WHERE create_time >= ?",
        (dep_start,),
    ).fetchall():
        if user_id is None:
            continue
        deposits_by_user[user_id].append({
            "date": create_time, "amount": order_amount, "status": status,
            "order_no": order_no, "channel": pay_channel,
        })

    withdrawals_by_user = defaultdict(list)
    for user_id, withdraw_amount, create_time, status, order_no, payment_channel in daily_conn.execute(
        "SELECT user_id, withdraw_amount, create_time, status, order_no, payment_channel FROM withdrawals WHERE create_time >= ?",
        (dep_start,),
    ).fetchall():
        if user_id is None:
            continue
        withdrawals_by_user[user_id].append({
            "date": create_time, "amount": withdraw_amount, "status": STATUS_LABELS.get(status, status),
            "order_no": order_no, "channel": payment_channel,
        })

    games_start = (today - timedelta(days=1)).isoformat()
    games_by_user = defaultdict(list)
    for user_id, game_name, change_value, create_time, direction in daily_conn.execute(
        "SELECT user_id, game_name, change_value, create_time, direction FROM wallet_transactions "
        "WHERE game_name IS NOT NULL AND game_name != '' AND create_time >= ? "
        "AND id NOT IN (SELECT id FROM bonuses)",
        (games_start,),
    ).fetchall():
        if user_id is None:
            continue
        # direction=1 = bet (debit), direction=0 = win payout (credit) --
        # change_value itself is always a positive magnitude in this data,
        # confirmed via an earlier diagnostic; direction carries the actual
        # sign, not change_value.
        games_by_user[user_id].append({
            "game_name": game_name, "amount": change_value,
            "type": "Win" if direction == 0 else "Bet", "date": create_time,
        })

    for d in deposits_by_user.values():
        d.sort(key=lambda r: r["date"], reverse=True)
    for d in withdrawals_by_user.values():
        d.sort(key=lambda r: r["date"], reverse=True)
    for d in games_by_user.values():
        d.sort(key=lambda r: r["date"], reverse=True)
        del d[15:]  # keep only the most recent 15 per user

    return deposits_by_user, withdrawals_by_user, games_by_user


def build_and_upload_user_search_index(mconn, recent_activity, creds, agent_by_user):
    """Sharded user-search index, rebuilt from scratch every run (cheap:
    everything needed is already local to this pipeline run, no extra
    network calls). Cloudflare Workers can't practically query a 224MB+
    SQLite file per search request -- 40 small JSON shard files in R2 let
    the dashboard's Search User page do one cheap R2 GET (shard =
    user_id % 40) instead. Every user in master_userlist.db gets an entry
    (even ones with zero activity, so a lookup for any valid ID gives a
    sensible "no recent activity" result rather than a 404); recent
    deposits/withdrawals/games are only present for users who have any."""
    deposits_by_user, withdrawals_by_user, games_by_user = recent_activity
    shards = [dict() for _ in range(USER_SEARCH_SHARDS)]
    # Phone is deliberately not selected/exposed here -- not displayed
    # anywhere on the dashboard.
    rows = mconn.execute(
        "SELECT user_id, city, channel, total_recharge, total_withdrawal, vip_level, "
        "user_balance, last_active_time, create_time FROM users"
    ).fetchall()
    for user_id, city, channel, total_recharge, total_withdrawal, vip_level, user_balance, last_active_time, create_time in rows:
        profile = {
            "user_id": user_id,
            "agent": agent_for(agent_by_user, user_id),
            "region": city,
            "acquisition_channel": channel,
            "vip_level": vip_level,
            "total_deposit": round(total_recharge or 0.0, 2),
            "total_withdraw": round(total_withdrawal or 0.0, 2),
            "wallet_balance": round(user_balance or 0.0, 2),
            "net_lifetime": round((total_recharge or 0.0) - (total_withdrawal or 0.0), 2),
            "last_active_time": last_active_time,
            "registered": create_time,
            "recent_deposits": deposits_by_user.get(user_id, []),
            "recent_withdrawals": withdrawals_by_user.get(user_id, []),
            "recent_games": games_by_user.get(user_id, []),
        }
        shards[user_id % USER_SEARCH_SHARDS][str(user_id)] = profile

    s3 = boto3.client(
        "s3",
        endpoint_url=creds["R2_ENDPOINT_URL"],
        aws_access_key_id=creds["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=creds["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    for i, shard in enumerate(shards):
        key = f"user_search/shard_{i:02d}.json"
        s3.put_object(Bucket=creds["R2_BUCKET"], Key=key, Body=json.dumps(shard), ContentType="application/json")
    print(f"Uploaded {USER_SEARCH_SHARDS} user search shards covering {len(rows)} users")


def bonus_claim_report(daily_db_path, deposit_rows, deposit_challenge_bonus_rows, today):
    """All bonuses claimed TODAY -- both wallet-sourced bonuses (Welcome
    Back, Loyalty, VIP tiers, Daily Active, etc., from daily_records.db's
    `bonuses` table) and the 3-Day Deposit Challenge Bonus (Rules 1-4).
    For each: claimed users, total bonus value, how many of those claimers
    ALSO made a COMPLETE deposit at any point today (a same-day "did the
    bonus convert into a deposit" signal) plus the actual amount they
    deposited (not just the headcount -- two converters aren't equally
    valuable if one deposited Rs200 and the other Rs20,000), and the
    resulting %.

    Scoped to today only. The permanent bonus_performance rollup (see
    compute_and_save_bonus_performance in api_pull_ingest.py) still tracks
    lifetime history for each category regardless of what this specific
    view surfaces.

    Learning about new bonuses: `bonuses` is populated by classify_bonus()
    (in ingest_update.py) under three confirmed rules -- a real bonus name
    in game_name with blank source (category = game_name); game_name
    literally "Elle Import Excel Add", using source_id for the real bonus
    identity (e.g. "Daily Active Low VIP"); or blank game_name with "bonus"
    in source_id, rolled up into combined "Daily Active Bonus"/"Daily
    Active Bonus Low" categories (stripping the random per-instance
    suffix). Any bonus matching one of these rules is picked up
    automatically the first day it appears -- no maintained name list, no
    code change needed."""
    today_str = today.isoformat()

    today_deposit_amount = defaultdict(float)
    for pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit in deposit_rows:
        if status != "COMPLETE" or user_id is None or not create_time:
            continue
        if str(create_time).startswith(today_str):
            today_deposit_amount[user_id] += order_amount or 0.0
    today_depositors = set(today_deposit_amount.keys())

    daily_conn = sqlite3.connect(daily_db_path)
    try:
        bonus_rows_today = daily_conn.execute(
            "SELECT matched_category, user_id, change_value, create_time FROM bonuses"
        ).fetchall()
    except sqlite3.OperationalError:
        bonus_rows_today = []  # bonuses table doesn't exist yet
    daily_conn.close()

    by_category = defaultdict(lambda: {"users": set(), "value": 0.0})
    for matched_category, user_id, change_value, create_time in bonus_rows_today:
        if not matched_category or not create_time or not str(create_time).startswith(today_str):
            continue
        b = by_category[matched_category]
        b["users"].add(user_id)
        b["value"] += change_value or 0.0

    def build_rows(groups):
        rows = []
        for category, b in groups.items():
            claimed_users = len(b["users"])
            converted_users = b["users"] & today_depositors
            converted = len(converted_users)
            deposit_amount = sum(today_deposit_amount[u] for u in converted_users)
            rows.append({
                "bonus_category": category,
                "claimed_users": claimed_users,
                "total_value": round(b["value"], 2),
                "deposited_after": converted,
                "deposit_amount": round(deposit_amount, 2),
                "pct_deposited": round(converted / claimed_users * 100, 2) if claimed_users else 0.0,
            })
        rows.sort(key=lambda r: -r["total_value"])
        return rows

    dcb_groups = defaultdict(lambda: {"users": set(), "value": 0.0})
    for r in deposit_challenge_bonus_rows:
        d = dcb_groups[r["rule"]]
        d["users"].add(r["user_id"])
        d["value"] += r["bonus_amount"]

    return {
        "wallet_bonuses": build_rows(by_category),
        "deposit_challenge_bonuses": build_rows(dcb_groups),
    }


# Weekly Cashback Shield (Action Center): loss amount Rs 5,000-500,000, tiered
# by what % of the week's deposit was "lost" (verified_loss / total_deposit).
# Ordered highest-threshold-first so the first match in weekly_cashback_shield
# below picks the correct (highest-earned) tier for a given loss_pct.
WEEKLY_CASHBACK_TIERS = [
    (100.0, 0.08),
    (75.0, 0.04),
    (50.0, 0.02),
]
WEEKLY_CASHBACK_MIN_LOSS = 5000.0
WEEKLY_CASHBACK_MAX_LOSS = 500000.0

# A separate, smaller-loss tier: Rs 500 up to (not including) the Rs 5,000
# floor above gets a flat 1% cashback -- but only if that loss is ALSO at
# least 80% of that week's deposit (a stricter bar than the 50% floor used
# by the 3 tiers above).
WEEKLY_CASHBACK_SMALL_LOSS_MIN = 500.0
WEEKLY_CASHBACK_SMALL_LOSS_MIN_PCT = 80.0
WEEKLY_CASHBACK_SMALL_LOSS_PCT = 0.01


def weekly_cashback_week_range(now):
    """Sunday-to-Saturday week window, matching the promo's own "credited
    every Sunday morning" cadence. Normally the Sun-Sat week containing
    `now`, EXCEPT on the cutover day itself (Sunday) before 22:00 IST --
    there, the dashboard keeps showing the just-completed week so admins
    have all Sunday morning/afternoon to review it before the display
    switches to tracking the new (barely-started) week."""
    today = now.date()
    days_since_sunday = (today.weekday() + 1) % 7  # Python: Monday=0 .. Sunday=6
    this_week_start = today - timedelta(days=days_since_sunday)
    if today == this_week_start and now.time() < dtime(22, 0):
        week_start = this_week_start - timedelta(days=7)
    else:
        week_start = this_week_start
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def weekly_cashback_shield(mconn, deposit_rows, withdrawal_rows, agent_by_user, now):
    """Weekly loss-protection cashback: for each user who deposited during
    the displayed Sun-Sat week (see weekly_cashback_week_range), verified
    loss = total_deposit - total_withdraw - CURRENT wallet balance -- money
    that came in this week and isn't sitting in their wallet or already
    paid back out, i.e. spent on betting activity. Two eligibility paths:
      - loss Rs 500-4,999.99: flat 1% cashback, but only if that's ALSO at
        least 80% of what they deposited that week.
      - loss Rs 5,000-500,000: needs to ALSO be at least 50% of what they
        deposited that week -- higher loss-% tiers earn a higher cashback
        rate (see WEEKLY_CASHBACK_TIERS).
    Only lists users who actually qualify this week, same convention as
    the other bonus/retention sections on this dashboard -- not a full
    audit of every depositor."""
    week_start, week_end = weekly_cashback_week_range(now)

    deposit_by_user = defaultdict(float)
    for pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit in deposit_rows:
        if status != "COMPLETE" or user_id is None or not create_time:
            continue
        dt = parse_dt(create_time)
        if dt and week_start <= dt.date() <= week_end:
            deposit_by_user[user_id] += order_amount or 0.0

    withdraw_by_user = defaultdict(float)
    for withdraw_amount, create_time, status, user_id, *_rest in withdrawal_rows:
        if status != 2 or user_id is None or not create_time:
            continue
        dt = parse_dt(create_time)
        if dt and week_start <= dt.date() <= week_end:
            withdraw_by_user[user_id] += withdraw_amount or 0.0

    user_ids = list(deposit_by_user.keys())
    vip_by_user, balance_by_user = {}, {}
    if user_ids:
        placeholders = ",".join("?" * len(user_ids))
        for uid, vip, bal in mconn.execute(
            f"SELECT user_id, vip_level, user_balance FROM users WHERE user_id IN ({placeholders})", user_ids
        ).fetchall():
            vip_by_user[uid] = vip
            balance_by_user[uid] = bal or 0.0

    rows = []
    for user_id, total_deposit in deposit_by_user.items():
        total_withdraw = withdraw_by_user.get(user_id, 0.0)
        balance = balance_by_user.get(user_id, 0.0)
        verified_loss = total_deposit - total_withdraw - balance
        if WEEKLY_CASHBACK_SMALL_LOSS_MIN <= verified_loss < WEEKLY_CASHBACK_MIN_LOSS:
            loss_pct = (verified_loss / total_deposit * 100) if total_deposit else 0.0
            if loss_pct < WEEKLY_CASHBACK_SMALL_LOSS_MIN_PCT:
                continue
            cashback_pct = WEEKLY_CASHBACK_SMALL_LOSS_PCT
        elif WEEKLY_CASHBACK_MIN_LOSS <= verified_loss <= WEEKLY_CASHBACK_MAX_LOSS:
            loss_pct = (verified_loss / total_deposit * 100) if total_deposit else 0.0
            cashback_pct = next((pct for threshold, pct in WEEKLY_CASHBACK_TIERS if loss_pct >= threshold), None)
            if cashback_pct is None:
                continue
        else:
            continue
        rows.append({
            "user_id": user_id,
            "agent": agent_for(agent_by_user, user_id),
            "vip": vip_by_user.get(user_id),
            "total_deposit": round(total_deposit, 2),
            "total_withdraw": round(total_withdraw, 2),
            "user_balance": round(balance, 2),
            "verified_loss": round(verified_loss, 2),
            "eligible_pct": round(cashback_pct * 100, 2),
            "bonus_amount": round(verified_loss * cashback_pct, 2),
        })
    rows.sort(key=lambda r: -r["bonus_amount"])

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "eligible_count": len(rows),
        "total_bonus": round(sum(r["bonus_amount"] for r in rows), 2),
        "rows": rows[:ACTION_CENTER_LIST_CAP],
    }


# Powers the "Performance" leaderboard: for each agent, per criterion, how
# much they achieved vs a daily target. Two shapes:
#   "count" -- a flat per-day headcount target (e.g. 7 reactivations/day).
#     Stored per day as (actual_count, target_count) so a date range just
#     sums both sides: pct = SUM(actual) / SUM(target) * 100.
#   "rate"  -- a percentage-of-cohort target (e.g. 30% retention). Stored
#     per day as (converted_count, cohort_size) -- NEVER the target itself
#     -- so a date range sums the raw counts and recomputes the TRUE
#     weighted rate (SUM(converted) / SUM(cohort) * 100), rather than
#     naively averaging daily percentages, which would be wrong whenever
#     cohort size varies day to day. That weighted rate is then compared
#     against the flat target here to get "% of target achieved".
AGENT_PERF_TARGETS = {
    "Reactivation Low": {"type": "count", "target": 20},
    "Reactivation High": {"type": "count", "target": 10},
    "Retention": {"type": "rate", "target": 30},
    "Low VIP Upgrade": {"type": "count", "target": 10},
    "High VIP Upgrade": {"type": "count", "target": 5},
    "Low Premium Active": {"type": "rate", "target": 35},
    "High Premium Active": {"type": "rate", "target": 35},
}

AGENT_PERF_RETENTION_DAYS = 35


def compute_agent_performance_rows(agent_list, reactivation, vip_upgrade, retention, premium_active, date_str):
    """One (date, agent, category, numerator, denominator) row per agent per
    the 7 Performance-page criteria, for TODAY specifically -- upserted into
    master_userlist.db's agent_performance table by main(). See
    AGENT_PERF_TARGETS for what numerator/denominator mean per category.

    `retention` here is specifically first_deposit_retention's result (by
    user request: the Performance page's single "Retention" criterion is
    First-Deposit retention only, not combined with Bonus-Claimer retention,
    which has no Low/High split to begin with)."""
    rows = []

    count_sources = {
        "Reactivation Low": reactivation["low"]["agent_breakdown"] if reactivation else {},
        "Reactivation High": reactivation["high"]["agent_breakdown"] if reactivation else {},
        "Low VIP Upgrade": vip_upgrade["low"]["agent_breakdown"] if vip_upgrade else {},
        "High VIP Upgrade": vip_upgrade["high"]["agent_breakdown"] if vip_upgrade else {},
    }
    for category, breakdown in count_sources.items():
        target = AGENT_PERF_TARGETS[category]["target"]
        for agent in agent_list:
            rows.append((date_str, agent, category, breakdown.get(agent, 0), target))

    ret_cohort = retention.get("cohort_by_agent", {}) if retention else {}
    ret_converted = retention.get("converted_by_agent", {}) if retention else {}
    for agent in agent_list:
        rows.append((date_str, agent, "Retention", ret_converted.get(agent, 0), ret_cohort.get(agent, 0)))

    for tier_label, category in [("low", "Low Premium Active"), ("high", "High Premium Active")]:
        tier = premium_active.get(tier_label, {}) if premium_active else {}
        cohort_by_agent = tier.get("cohort_by_agent", {})
        converted_by_agent = tier.get("converted_by_agent", {})
        for agent in agent_list:
            rows.append((date_str, agent, category, converted_by_agent.get(agent, 0), cohort_by_agent.get(agent, 0)))

    return rows


def main():
    # Source timestamps (create_time, last_active_time, etc.) are IST, but this
    # script runs on a UTC-clocked GitHub Actions runner -- datetime.now() would
    # be ~5.5h behind IST, making very recent activity look like it's in the
    # future (negative inactive_days/hours). Compute "now" in IST to match.
    now = datetime.utcnow() + timedelta(hours=5, minutes=30)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    deposit_rows = cur.execute(
        "SELECT pay_channel, order_amount, create_time, update_time, status, user_id, is_first_deposit FROM deposits"
    ).fetchall()
    withdrawal_rows = cur.execute(
        "SELECT withdraw_amount, create_time, status, user_id, payment_channel, review_time, update_time, order_no, "
        "payment_center_order_id FROM withdrawals"
    ).fetchall()
    wallet_rows = cur.execute(
        "SELECT user_id, create_time FROM wallet_transactions WHERE user_id IS NOT NULL"
    ).fetchall()
    channel_performance = channel_performance_report(conn, now.date())
    recent_activity = build_recent_activity_by_user(conn, now.date())
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
    agent_by_user = {}
    action_center = None
    weekly_cashback = None
    reactivation = None
    vip_upgrade = None
    performance = None
    profit_users = None
    master_db_path = os.path.join(BASE, "master_userlist.db")
    if os.path.exists(master_db_path):
        mconn = sqlite3.connect(master_db_path)
        total_registered_users = mconn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        vip_by_user = dict(mconn.execute("SELECT user_id, vip_level FROM users").fetchall())
        city_by_user = dict(mconn.execute("SELECT user_id, city FROM users").fetchall())
        try:
            agent_by_user = dict(mconn.execute("SELECT user_id, agent_name FROM agent_assignments").fetchall())
        except sqlite3.OperationalError:
            agent_by_user = {}  # table doesn't exist yet -- pre-dates this feature
        action_center = action_center_reports(mconn, now, agent_by_user)
        weekly_cashback = weekly_cashback_shield(mconn, deposit_rows, withdrawal_rows, agent_by_user, now)
        fallback_creds = load_creds()
        reactivation_candidates_path = os.path.join(BASE, "reactivation_candidates.json")
        reactivation_candidates = load_json_with_r2_fallback(
            reactivation_candidates_path, "reports/reactivation_candidates.json", fallback_creds, []
        )
        reactivation = deposit_reactivation_analytics(mconn, reactivation_candidates, action_center, agent_by_user)
        vip_upgrade_path = os.path.join(BASE, "vip_upgrade_candidates.json")
        vip_upgrade_candidates = load_json_with_r2_fallback(
            vip_upgrade_path, "reports/vip_upgrade_candidates.json", fallback_creds, {"low": [], "high": []}
        )
        vip_upgrade = vip_upgrade_analytics(vip_upgrade_candidates, action_center, agent_by_user)

        # Conversion funnels (3-day/7-day: of users near-upgrade/inactive N
        # days ago, how many have since converted) -- computed once/day by
        # api_pull_ingest.py's sync_master_userlist and persisted directly in
        # master_userlist.db, so this is just a cheap read, not a recompute.
        try:
            funnel_row = mconn.execute("SELECT data FROM funnel_stats").fetchone()
        except sqlite3.OperationalError:
            funnel_row = None  # table doesn't exist yet -- pre-dates this feature
        if funnel_row:
            funnel_data = json.loads(funnel_row[0])
            reactivation["funnel"] = funnel_data.get("reactivation")
            vip_upgrade["funnel"] = funnel_data.get("vip_upgrade")

        performance = performance_history(mconn)
        profit_users = profit_users_of_the_day(mconn, deposit_rows, withdrawal_rows, now, agent_by_user)
        build_and_upload_user_search_index(mconn, recent_activity, load_creds(), agent_by_user)

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

    for withdraw_amount, create_time, status, user_id, payment_channel, review_time, update_time, order_no, payment_center_order_id in withdrawal_rows:
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
            "payment_center_order_id": payment_center_order_id,
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
            "withdrawal_orders": withdrawal_orders_export(by_date_withdrawal_full.get(date, []), vip_by_user, now, agent_by_user),
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

    deposit_challenge_bonus_rows = deposit_challenge_bonus(deposit_rows, build_deposit_day_stats(deposit_rows), now.date(), agent_by_user)
    action_center_extra = {
        "yesterday_first_deposit_users": yesterday_first_deposit_users(deposit_rows, all_withdrawal_full, vip_by_user, city_by_user, now.date(), agent_by_user),
        "deposit_challenge_bonus": deposit_challenge_bonus_rows,
    }

    retention = {
        "first_deposit": first_deposit_retention(deposit_rows, city_by_user, now.date(), agent_by_user),
        "bonus_claimer": bonus_claimer_retention(deposit_challenge_bonus_rows, deposit_rows, city_by_user, now.date(), agent_by_user),
    }

    premium_active = None
    if os.path.exists(master_db_path):
        mconn3 = sqlite3.connect(master_db_path)
        premium_active = premium_active_conversion(mconn3, deposit_rows, now, agent_by_user)
        mconn3.close()

    bonus_claims = bonus_claim_report(DB_PATH, deposit_rows, deposit_challenge_bonus_rows, now.date())

    # Persist today's per-agent performance, then read back the full rolling
    # window for the Performance page -- small enough (agents x 7 categories
    # x up to 35 days) to ship in full and let the frontend do date-range
    # filtering/aggregation client-side, same pattern as premium_active etc.
    agent_list = sorted(set(agent_by_user.values()))
    agent_performance_rows = []
    if os.path.exists(master_db_path) and agent_list:
        mconn4 = sqlite3.connect(master_db_path)
        mconn4.execute(
            "CREATE TABLE IF NOT EXISTS agent_performance ("
            "date TEXT, agent_name TEXT, category TEXT, numerator REAL, denominator REAL, "
            "PRIMARY KEY (date, agent_name, category))"
        )
        upsert_rows = compute_agent_performance_rows(
            agent_list, reactivation, vip_upgrade, retention["first_deposit"], premium_active, now.date().isoformat()
        )
        mconn4.executemany(
            "INSERT OR REPLACE INTO agent_performance (date, agent_name, category, numerator, denominator) "
            "VALUES (?, ?, ?, ?, ?)",
            upsert_rows,
        )
        # Rolling 35-day retention -- ISO date strings compare lexicographically,
        # so a plain string cutoff works without parsing.
        cutoff = (now.date() - timedelta(days=AGENT_PERF_RETENTION_DAYS)).isoformat()
        mconn4.execute("DELETE FROM agent_performance WHERE date < ?", (cutoff,))
        mconn4.commit()
        agent_performance_rows = mconn4.execute(
            "SELECT date, agent_name, category, numerator, denominator FROM agent_performance ORDER BY date"
        ).fetchall()
        mconn4.close()
    agent_performance = [
        {"date": d, "agent": a, "category": c, "numerator": n, "denominator": den}
        for d, a, c, n, den in agent_performance_rows
    ]

    region_vip_analytics_data = region_vip_deposit_analytics(by_date_records, by_date_withdrawals, city_by_user, vip_by_user, all_dates)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        # The exact IST calendar date used as "today" for Reactivation, VIP
        # Upgrade, and Retention -- those three sections are always scoped to
        # this date (never affected by the Region/VIP chart's date-switch,
        # which only re-renders that chart), refreshed on the next pipeline
        # run after midnight IST. Exposed so the frontend can label it
        # explicitly rather than leaving it implicit.
        "report_today": now.date().isoformat(),
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
        # All-dates raw order rows (unlike by_date[...].withdrawal_orders,
        # which is scoped to a single selected date) -- needed for the
        # Processing/In-Review aging charts and the Last-4-Days completed
        # chart, which all span the whole retained window, not one day.
        "withdrawal_orders_full": withdrawal_orders_export(all_withdrawal_full, vip_by_user, now, agent_by_user),
        "action_center": action_center,
        "action_center_extra": action_center_extra,
        "weekly_cashback_shield": weekly_cashback,
        "region_vip_analytics": region_vip_analytics_data,
        "reactivation": reactivation,
        "vip_upgrade": vip_upgrade,
        "retention": retention,
        "premium_active": premium_active,
        "performance_history": performance,
        "profit_users": profit_users,
        "channel_performance": channel_performance,
        "bonus_claims": bonus_claims,
        # Distinct real agent names (never includes AGENT_UNASSIGNED) -- powers
        # the Reassign Agent dropdown on the Search User page and the
        # Performance leaderboard.
        "agent_list": agent_list,
        # Rolling 35-day per-agent-per-category numerator/denominator rows --
        # the Performance page does all date-range filtering/aggregation and
        # "% of target achieved" math client-side from this.
        "agent_performance": agent_performance,
        "agent_performance_targets": AGENT_PERF_TARGETS,
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

    # Per-date snapshot of Analytics' Reactivation/VIP Upgrade/Retention/
    # Premium Active sections -- these are single "as of today" computations,
    # overwritten every run, so browsing to a past date on the Analytics page
    # needs its own copy of that day's numbers. Kept as a SEPARATE small R2
    # object per day (not embedded in the ~7MB main deposit_report.json)
    # so switching dates is a small on-demand fetch, matching the same
    # last-7-dates window region_vip_analytics already uses for consistency.
    today_str = now.date().isoformat()
    snapshot = {
        "date": today_str,
        "reactivation": reactivation,
        "vip_upgrade": vip_upgrade,
        "retention": retention,
        "premium_active": premium_active,
    }
    snapshot_key = f"reports/analytics_history/{today_str}.json"
    s3.put_object(Bucket=creds["R2_BUCKET"], Key=snapshot_key, Body=json.dumps(snapshot), ContentType="application/json")
    print(f"Uploaded {snapshot_key}")

    keep_dates = set(all_dates[-7:])
    listing = s3.list_objects_v2(Bucket=creds["R2_BUCKET"], Prefix="reports/analytics_history/")
    purged = 0
    for obj in listing.get("Contents", []):
        key = obj["Key"]
        obj_date = key.rsplit("/", 1)[-1].replace(".json", "")
        if obj_date not in keep_dates:
            s3.delete_object(Bucket=creds["R2_BUCKET"], Key=key)
            purged += 1
    print(f"Purged {purged} analytics_history snapshots outside the last {len(keep_dates)} dates")


if __name__ == "__main__":
    main()
