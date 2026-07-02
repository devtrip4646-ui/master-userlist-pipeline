"""
Runs inside GitHub Actions. Downloads the current DBs + one newly-uploaded
Excel file from R2, ingests it via ingest_update.py, then re-uploads the
updated DBs to R2. The incoming file is deleted from R2 afterwards.

Usage: python3 ci_ingest.py --file-type userlist --key incoming/userlist/foo.xlsx
"""
import argparse
import os
import sys
import boto3

BASE = os.path.dirname(os.path.abspath(__file__))


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT_URL"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file-type", required=True, choices=["userlist", "deposits", "withdrawals", "wallet"])
    ap.add_argument("--key", required=True, help="R2 object key of the uploaded xlsx file")
    args = ap.parse_args()

    bucket = os.environ["R2_BUCKET"]
    s3 = r2_client()

    # Pull down existing DBs (if present) so we ingest into the live state
    for fname in ["master_userlist.db", "daily_records.db"]:
        local_path = os.path.join(BASE, fname)
        try:
            s3.download_file(bucket, fname, local_path)
            print(f"Downloaded existing {fname} from R2")
        except Exception as e:
            print(f"No existing {fname} in R2 ({e}); will be created fresh")

    # Pull down the newly uploaded file
    local_incoming = os.path.join(BASE, os.path.basename(args.key))
    s3.download_file(bucket, args.key, local_incoming)
    print(f"Downloaded incoming file {args.key} -> {local_incoming}")

    # Run the ingest (this also purges >33 days and uploads both DBs to R2)
    flag_map = {
        "userlist": "--userlist",
        "deposits": "--deposits",
        "withdrawals": "--withdrawals",
        "wallet": "--wallet",
    }
    cmd_flag = flag_map[args.file_type]
    os.system(f'{sys.executable} {os.path.join(BASE, "ingest_update.py")} {cmd_flag} "{local_incoming}"')

    # Clean up the incoming file from R2 now that it's been processed
    s3.delete_object(Bucket=bucket, Key=args.key)
    print(f"Deleted processed file from R2: {args.key}")


if __name__ == "__main__":
    main()
