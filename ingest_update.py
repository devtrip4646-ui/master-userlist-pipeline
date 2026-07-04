"""
Ongoing ingest script for Master Userlist + Daily Records.

Usage:
  python3 ingest_update.py --userlist lotteryUserInfo_A.xlsx lotteryUserInfo_B.xlsx
  python3 ingest_update.py --deposits water_new.xlsx
  python3 ingest_update.py --withdrawals withdraw_new.xlsx
  python3 ingest_update.py --wallet detail_new1.xlsx detail_new2.xlsx
  python3 ingest_update.py --deposits a.xlsx --withdrawals b.xlsx --wallet c.xlsx --userlist d.xlsx

Any combination of the four flags can be passed in one run. After ingest, Daily
Records tables are purged to a rolling 33-day window (by create_time), and both
DBs are re-uploaded to R2 automatically unless --no-upload is passed.
"""
import argparse
import os
import re
import sqlite3
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
MASTER_DB = os.path.join(BASE, "master_userlist.db")
DAILY_DB = os.path.join(BASE, "daily_records.db")
RETENTION_DAYS = 33

import openpyxl


def clean(row):
    return tuple(str(v) if hasattr(v, "isoformat") else v for v in row)


def load_sheet(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))
    header = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    wb.close()
    return header, rows


def already_ingested(conn, filename):
    conn.execute("CREATE TABLE IF NOT EXISTS ingested_files (filename TEXT PRIMARY KEY, ingested_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    row = conn.execute("SELECT 1 FROM ingested_files WHERE filename = ?", (os.path.basename(filename),)).fetchone()
    return row is not None


def mark_ingested(conn, filename):
    conn.execute("INSERT OR IGNORE INTO ingested_files (filename) VALUES (?)", (os.path.basename(filename),))


def ingest_userlist(files):
    conn = sqlite3.connect(MASTER_DB)
    cur = conn.cursor()
    n_cols = len(cur.execute("PRAGMA table_info(users)").fetchall())
    update_time_idx = n_cols - 2
    updated, inserted, skipped_files = 0, 0, 0
    for f in files:
        if already_ingested(conn, f):
            print(f"  skip (already ingested): {f}")
            skipped_files += 1
            continue
        _, rows = load_sheet(f)
        for row in rows:
            if row[0] is None:
                continue
            row = clean(list(row))
            row[0] = int(float(row[0]))
            uid = row[0]
            existing = cur.execute("SELECT update_time FROM users WHERE user_id = ?", (uid,)).fetchone()
            if existing is None:
                cur.execute(f"INSERT INTO users VALUES ({','.join(['?']*n_cols)})", row)
                inserted += 1
            else:
                new_ut, old_ut = row[update_time_idx], existing[0]
                if new_ut is not None and (old_ut is None or str(new_ut) > str(old_ut)):
                    cur.execute(f"INSERT OR REPLACE INTO users VALUES ({','.join(['?']*n_cols)})", row)
                    updated += 1
        mark_ingested(conn, f)
        conn.commit()
    print(f"Master Userlist: {inserted} new, {updated} updated, {skipped_files} files already ingested")
    conn.close()


def ingest_deposits(files):
    # INSERT OR REPLACE (not IGNORE): a re-fetched deposit with the same id but a
    # changed status (e.g. pending -> COMPLETE some hours/days later) must overwrite
    # the existing row, not be silently skipped.
    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()
    n_cols = len(cur.execute("PRAGMA table_info(deposits)").fetchall())
    added = 0
    for f in files:
        if already_ingested(conn, f):
            print(f"  skip (already ingested): {f}")
            continue
        _, rows = load_sheet(f)
        cur.executemany(f"INSERT OR REPLACE INTO deposits VALUES ({','.join(['?']*n_cols)})", [clean(r) for r in rows])
        added += cur.rowcount
        mark_ingested(conn, f)
        conn.commit()
    print(f"Deposits: {added} rows processed (new + updated)")
    conn.close()


def ingest_withdrawals(files):
    # INSERT OR REPLACE (not IGNORE): a re-fetched withdrawal with the same id but a
    # changed status (In-Review/Processing -> Complete/Rejected/Failed, possibly days
    # later) must overwrite the existing row, not be silently skipped.
    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()
    n_cols = len(cur.execute("PRAGMA table_info(withdrawals)").fetchall())
    added = 0
    for f in files:
        if already_ingested(conn, f):
            print(f"  skip (already ingested): {f}")
            continue
        _, rows = load_sheet(f)
        cur.executemany(f"INSERT OR REPLACE INTO withdrawals VALUES ({','.join(['?']*n_cols)})", [clean(r) for r in rows])
        added += cur.rowcount
        mark_ingested(conn, f)
        conn.commit()
    print(f"Withdrawals: {added} rows processed (new + updated)")
    conn.close()


CANONICAL_BONUSES = [
    "Welcome Back Bonus", "Loyalty Bonus", "First deposit", "Second Deposit",
    "Third deposit", "Fourth deposit", "Low VIP", "Mid VIP", "High VIP", "Super VIP",
    "Evolution Live Betting Bonus", "Daily Active Bonus", "Daily Active Bonus Low",
]


def normalize(s):
    return re.sub(r"\s+", " ", str(s).strip().lower())


# Real games that happen to have "bonus" in their name (a bonus ROUND within
# the game, not a wallet bonus payout) -- the generic "bonus" keyword
# fallback below would otherwise misclassify these as bonus payouts.
# Confirmed false positives: "Chicken Road Bonus" and "Bonus Hunter" are
# both real games, not bonuses.
KNOWN_GAME_FALSE_POSITIVES = {"chicken road bonus", "bonus hunter"}


def classify_bonus(game_name):
    canon_norm = {normalize(c): c for c in CANONICAL_BONUSES}
    norm = normalize(game_name)
    if norm in KNOWN_GAME_FALSE_POSITIVES:
        return None
    deposit_ordinal = re.compile(r"^(first|second|third|fourth|fifth)\s+deposit$", re.I)
    vip_tier = re.compile(r"^(low|mid|high|super)\s*vip$", re.I)
    vip_week_or_level = re.compile(r"vip\s*(week|level)", re.I)
    if norm in canon_norm:
        return canon_norm[norm]
    if deposit_ordinal.match(str(game_name).strip()):
        return game_name
    if vip_tier.match(str(game_name).strip()):
        return game_name
    if vip_week_or_level.search(str(game_name)):
        return game_name
    if "bonus" in norm and ":" not in str(game_name):
        return game_name
    return None


def ingest_wallet(files):
    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()
    n_cols = len(cur.execute("PRAGMA table_info(wallet_transactions)").fetchall())
    # bonuses is normally created once by the original bootstrap (build_daily_records.py),
    # not by this ongoing script -- IF NOT EXISTS here so a from-scratch daily_records.db
    # doesn't fail on the INSERT below.
    cur.execute(
        "CREATE TABLE IF NOT EXISTS bonuses ("
        "id INTEGER PRIMARY KEY, user_id INTEGER, bonus_name TEXT, matched_category TEXT, "
        "change_value REAL, change_after REAL, create_time TEXT, source TEXT)"
    )
    # Retroactive cleanup: rows already classified as "Chicken Road Bonus" /
    # "Bonus Hunter" (real games, not bonuses -- see KNOWN_GAME_FALSE_POSITIVES
    # above) before that exclusion existed. Fixing classify_bonus() alone only
    # stops NEW rows from being misclassified going forward; already-ingested
    # rows for today and recent days need to be removed explicitly, or reports
    # reading straight from `bonuses` would keep showing them for weeks until
    # they age out of the 33-day window on their own. Safe to run every time
    # (a no-op once these are gone).
    cur.execute(
        "DELETE FROM bonuses WHERE bonus_name IN ('Chicken Road Bonus', 'Bonus Hunter') "
        "OR matched_category IN ('Chicken Road Bonus', 'Bonus Hunter')"
    )
    conn.commit()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bonus_user ON bonuses(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bonus_name ON bonuses(bonus_name)")
    added = 0
    new_bonus_rows = []
    for f in files:
        if already_ingested(conn, f):
            print(f"  skip (already ingested): {f}")
            continue
        _, rows = load_sheet(f)
        for row in rows:
            row = clean(row)
            cur.execute(f"INSERT OR IGNORE INTO wallet_transactions VALUES ({','.join(['?']*n_cols)})", row)
            if cur.rowcount:
                added += 1
                _id, game_name, user_id = row[0], row[1], row[2]
                change_value, change_after = row[5], row[6]
                create_time, source = row[17], row[12]
                if game_name:
                    matched = classify_bonus(game_name)
                    if matched:
                        new_bonus_rows.append((_id, user_id, game_name, matched, change_value, change_after, create_time, source))
        mark_ingested(conn, f)
        conn.commit()
    if new_bonus_rows:
        cur.executemany(
            "INSERT OR IGNORE INTO bonuses (id, user_id, bonus_name, matched_category, change_value, change_after, create_time, source) VALUES (?,?,?,?,?,?,?,?)",
            new_bonus_rows,
        )
        conn.commit()
    print(f"Wallet transactions: {added} rows added, {len(new_bonus_rows)} classified as bonuses")
    conn.close()


def purge_old_daily_records():
    conn = sqlite3.connect(DAILY_DB)
    cur = conn.cursor()
    cutoff = f"datetime('now', '-{RETENTION_DAYS} days')"
    for table, time_col in [("deposits", "create_time"), ("withdrawals", "create_time"),
                             ("wallet_transactions", "create_time"), ("bonuses", "create_time")]:
        cur.execute(f"DELETE FROM {table} WHERE {time_col} IS NOT NULL AND datetime({time_col}) < {cutoff}")
        print(f"Purged {cur.rowcount} rows from {table} (older than {RETENTION_DAYS} days)")
    conn.commit()
    conn.execute("VACUUM")
    conn.close()


def upload_to_r2(files):
    subprocess.run([sys.executable, os.path.join(BASE, "upload_to_r2.py"), "--files"] + files, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--userlist", nargs="*", default=[])
    ap.add_argument("--deposits", nargs="*", default=[])
    ap.add_argument("--withdrawals", nargs="*", default=[])
    ap.add_argument("--wallet", nargs="*", default=[])
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--no-purge", action="store_true")
    args = ap.parse_args()

    if args.userlist:
        ingest_userlist(args.userlist)
    if args.deposits:
        ingest_deposits(args.deposits)
    if args.withdrawals:
        ingest_withdrawals(args.withdrawals)
    if args.wallet:
        ingest_wallet(args.wallet)

    if not args.no_purge:
        purge_old_daily_records()

    if not args.no_upload:
        # Only upload DBs that were actually touched this run -- master_userlist.db is
        # 200MB+ and rarely changes; re-uploading it on every deposits/withdrawals/wallet
        # pull wastes minutes on the scheduled pipeline for no reason.
        touched = []
        if args.userlist:
            touched.append("master_userlist.db")
        if args.deposits or args.withdrawals or args.wallet:
            touched.append("daily_records.db")
        if touched:
            upload_to_r2(touched)


if __name__ == "__main__":
    main()
