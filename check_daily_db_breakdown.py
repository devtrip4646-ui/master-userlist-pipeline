"""One-off read-only diagnostic: table-by-table size and row-count
breakdown of daily_records.db (via SQLite's dbstat virtual table where
available, else row counts + column info only), plus a look at which
columns each report-consuming table actually needs vs. how many it
carries, to inform a size-reduction plan. Writes results to
debug/daily_db_breakdown.json and commits it back to the repo. One-off;
delete both this script and its workflow after use.
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

    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]

    dbstat_available = True
    size_by_table = {}
    try:
        for name, size in cur.execute(
            "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name"
        ).fetchall():
            size_by_table[name] = size
    except sqlite3.OperationalError:
        dbstat_available = False

    page_count, page_size = cur.execute("PRAGMA page_count").fetchone()[0], cur.execute("PRAGMA page_size").fetchone()[0]
    total_file_bytes = page_count * page_size
    freelist_count = cur.execute("PRAGMA freelist_count").fetchone()[0]

    result = {
        "total_file_bytes": total_file_bytes,
        "total_file_mb": round(total_file_bytes / (1024 * 1024), 2),
        "freelist_pages": freelist_count,
        "freelist_mb_reclaimable_by_vacuum": round(freelist_count * page_size / (1024 * 1024), 2),
        "dbstat_available": dbstat_available,
        "tables": [],
    }

    for t in tables:
        row_count = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        cols = cur.execute(f"PRAGMA table_info({t})").fetchall()
        col_names = [c[1] for c in cols]
        indexes = cur.execute(f"PRAGMA index_list({t})").fetchall()
        entry = {
            "table": t,
            "row_count": row_count,
            "column_count": len(col_names),
            "columns": col_names,
            "index_count": len(indexes),
        }
        # dbstat name for a table's data includes indexes as separate rows
        # named after the index -- sum the table's own row plus any index
        # whose origin table matches, using sqlite_master to resolve that.
        if dbstat_available:
            own_size = size_by_table.get(t, 0)
            idx_names = [idx[1] for idx in indexes]
            idx_size = sum(size_by_table.get(ix, 0) for ix in idx_names)
            entry["table_data_mb"] = round(own_size / (1024 * 1024), 2)
            entry["index_mb"] = round(idx_size / (1024 * 1024), 2)
            entry["total_mb"] = round((own_size + idx_size) / (1024 * 1024), 2)
        result["tables"].append(entry)

    result["tables"].sort(key=lambda e: -e.get("total_mb", e["row_count"]))

    conn.close()

    out_path = os.path.join(BASE, "debug")
    os.makedirs(out_path, exist_ok=True)
    with open(os.path.join(out_path, "daily_db_breakdown.json"), "w") as f:
        json.dump(result, f, indent=2, default=str)

    subprocess.run(["git", "config", "user.email", "pipeline@bot.local"], check=True)
    subprocess.run(["git", "config", "user.name", "pipeline-bot"], check=True)
    subprocess.run(["git", "add", "debug/daily_db_breakdown.json"], check=True)
    subprocess.run(["git", "commit", "-m", "debug: daily_records.db size breakdown"], check=True)
    subprocess.run(["git", "push"], check=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
