"""
Shared helpers for the "Ban User" feature -- banned_users lives in
master_userlist.db and is the single source of truth for who's banned.
Imported by both ingest_update.py and api_pull_ingest.py so a banned user's
records are purged (and never re-created) no matter which ingestion path
touches them: manual dashboard file uploads, the hourly business API pull,
or a future one-off script.
"""
import sqlite3


def get_banned_user_ids(master_db_path):
    conn = sqlite3.connect(master_db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY, banned_at TEXT)")
    conn.commit()
    ids = [r[0] for r in conn.execute("SELECT user_id FROM banned_users").fetchall()]
    conn.close()
    return ids


def purge_banned_users(master_db_path, daily_db_path):
    """Deletes every trace of currently-banned users from both DBs. Called at
    the end of every ingestion run (see ingest_update.py's main()) so a ban
    stays permanent even if a fresh userlist/deposit/withdrawal/wallet file
    (or the hourly API pull) brings in new rows for that user_id afterward.
    Returns (master_touched, daily_touched)."""
    banned = get_banned_user_ids(master_db_path)
    if not banned:
        return False, False
    placeholders = ",".join("?" * len(banned))

    mconn = sqlite3.connect(master_db_path)
    mcur = mconn.cursor()
    master_touched = False
    for table in ["users", "agent_assignments", "balance_adjustments"]:
        try:
            mcur.execute(f"DELETE FROM {table} WHERE user_id IN ({placeholders})", banned)
            if mcur.rowcount:
                master_touched = True
                print(f"Purged {mcur.rowcount} banned-user row(s) from {table}")
        except sqlite3.OperationalError:
            pass  # table doesn't exist yet in this DB snapshot
    mconn.commit()
    mconn.close()

    dconn = sqlite3.connect(daily_db_path)
    dcur = dconn.cursor()
    daily_touched = False
    for table in ["deposits", "withdrawals", "wallet_transactions", "bonuses"]:
        try:
            dcur.execute(f"DELETE FROM {table} WHERE user_id IN ({placeholders})", banned)
            if dcur.rowcount:
                daily_touched = True
                print(f"Purged {dcur.rowcount} banned-user row(s) from {table}")
        except sqlite3.OperationalError:
            pass
    dconn.commit()
    dconn.close()
    return master_touched, daily_touched
