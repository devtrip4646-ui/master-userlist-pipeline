import json
import os
from collections import Counter

import boto3

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)
bucket = os.environ["R2_BUCKET"]
obj = s3.get_object(Bucket=bucket, Key="reports/deposit_report.json")
d = json.loads(obj["Body"].read())


def bucket_inactive_days(rows, edges):
    """edges e.g. [(0,7),(8,15),(16,30),(31,60),(61,90),(91,None)]"""
    out = {}
    for lo, hi in edges:
        label = f"{lo}-{hi}" if hi is not None else f"{lo}+"
        out[label] = sum(1 for r in rows if lo <= r["inactive_days"] <= (hi if hi is not None else 10**9))
    return out


ac = d.get("action_center") or {}
action_center_summary = {}
for key in ["near_upgrade_low", "near_upgrade_high", "inactive_high", "inactive_low", "active_low", "active_high"]:
    section = ac.get(key) or {}
    rows = section.get("rows") or []
    days = [r.get("inactive_days") for r in rows if r.get("inactive_days") is not None]
    action_center_summary[key] = {
        "total_matching": section.get("total_matching"),
        "min_days": min(days) if days else None,
        "max_days": max(days) if days else None,
    }

bonus_by_date = d.get("bonus_claims_by_date") or {}
bonus_summary_by_date = {}
for date_str, payload in bonus_by_date.items():
    wallet = payload.get("wallet_bonuses") or []
    dcb = payload.get("deposit_challenge_bonuses") or []
    bonus_summary_by_date[date_str] = {
        "wallet_claimed_users": sum(c.get("claimed_users", 0) for c in wallet),
        "wallet_total_value": sum(c.get("total_value", 0) for c in wallet),
        "wallet_deposited_after": sum(c.get("deposited_after", 0) for c in wallet),
        "dcb_count": len(dcb),
    }

wa = d.get("withdrawal_analysis") or {}
withdrawal_summary = {
    "processing_backlog": wa.get("processing_backlog"),
    "inreview_backlog": wa.get("inreview_backlog"),
    "last4days_completion": wa.get("last4days_completion"),
    "backlog_as_of": wa.get("backlog_as_of"),
}

reactivation = d.get("reactivation") or {}
reactivation_summary = {
    k: {kk: vv for kk, vv in (v or {}).items() if kk != "rows"}
    for k, v in reactivation.items()
} if isinstance(reactivation, dict) else reactivation

vip_upgrade = d.get("vip_upgrade") or {}
vip_upgrade_summary = {
    k: ({kk: vv for kk, vv in (v or {}).items() if kk != "rows"} if isinstance(v, dict) else v)
    for k, v in vip_upgrade.items()
} if isinstance(vip_upgrade, dict) else vip_upgrade

wcs = d.get("weekly_cashback_shield") or {}
wcs_rows = wcs.get("rows") if isinstance(wcs, dict) else None
wcs_summary = {
    "count": len(wcs_rows) if wcs_rows is not None else None,
    "total_cashback": sum(r.get("cashback_amount", 0) for r in wcs_rows) if wcs_rows else None,
}

out = {
    "report_today": d.get("report_today"),
    "latest_record_time": d.get("latest_record_time"),
    "dates": d.get("dates"),
    "withdrawal_analysis_summary": withdrawal_summary,
    "channel_performance": d.get("channel_performance"),
    "bonus_summary_by_date": bonus_summary_by_date,
    "reactivation_summary": reactivation_summary,
    "vip_upgrade_summary": vip_upgrade_summary,
    "weekly_cashback_shield_summary": wcs_summary,
    "agent_performance_targets": d.get("agent_performance_targets"),
    "action_center_summary": action_center_summary,
    "withdrawal_amount_range_by_day": d.get("withdrawal_amount_range_by_day"),
    "total_registered_users": d.get("total_registered_users"),
}

payload = json.dumps(out, default=str)
print("PAYLOAD_LENGTH:", len(payload))
print("=== DIAGNOSTICS_JSON_START ===")
print(payload)
print("=== DIAGNOSTICS_JSON_END ===")
