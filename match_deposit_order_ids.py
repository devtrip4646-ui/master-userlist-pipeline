"""
Read-only one-off: cross-reference a list of payment-gateway order IDs
(the DI...-prefixed "order_no" in deposits) against daily_records.db to see
which of them have a matching deposit record, and if so, its payment-center
order number, amount, channel, and status.
"""
import json
import os
import sqlite3

import boto3

BASE = os.path.dirname(os.path.abspath(__file__))
DAILY_DB = os.path.join(BASE, "daily_records.db")

ORDER_IDS = [
    "DI2026072123400007", "DI2026072123320005", "DI2026072122400005", "DI2026072123060012", "DI2026072122550003",
    "DI2026072122530013", "DI2026072122480003", "DI2026072122500005", "DI2026072121290010", "DI2026072121190005",
    "DI2026072114470004", "DI2026072117470001", "DI2026072117390004", "DI2026072117310002", "DI2026072116270011",
    "DI2026072116180007", "DI2026072115170007", "DI2026072115160010", "DI2026072115090011", "DI2026072114050008",
    "DI2026072114210007", "DI2026072114170001", "DI2026072114130011", "DI2026072113590004", "DI2026072111120008",
    "DI2026072110210005", "DI2026072103290001", "DI2026072102360005", "DI2026072023470011", "DI2026072022460006",
    "DI2026070821530005", "DI2026072022440017", "DI2026072022150010", "DI2026071923100005", "DI2026072020240002",
    "DI2026072018320004", "DI2026070517470007", "DI2026072017430005", "DI2026072015350001", "DI2026072015080005",
    "DI2026072015080002", "DI2026072014290004", "DI2026072014050002", "DI2026072014010012", "DI2026072013550007",
    "DI2026072012210006", "DI2026072012090007", "DI2026072011010008", "DI2026072010390005", "DI2026072010230002",
    "DI2026072000040008", "DI2026071923200031", "DI2026071919300007", "DI2026071923100008", "DI2026071923340001",
    "DI2026071923240005", "DI2026071923140014", "DI2026071921370007", "DI2026071922070005", "DI2026071921290016",
    "DI2026071921100007", "DI2026071921010001", "DI2026071920220002", "DI2026071914440020", "DI2026071917380008",
    "DI2026071917440005", "DI2026071917370009", "DI2026071912510011", "DI2026071719130012", "DI2026071915200015",
    "DI2026071900290013", "DI2026071913520002", "DI2026071912570013", "DI2026071912210009", "DI2026071911080003",
    "DI2026071910230002", "DI2026071900180008", "DI2026071900560017", "DI2026071907190002", "DI2026071814300001",
    "DI2026071822200013", "DI2026071805540002", "DI2026071823190010", "DI2026071904050002", "DI2026071722240011",
    "DI2026071900510005", "DI2026071822390016", "DI2026071900000001", "DI2026071900060001", "DI2026071900010006",
]

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["R2_ENDPOINT_URL"],
    aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    region_name="auto",
)
bucket = os.environ["R2_BUCKET"]
s3.download_file(bucket, "daily_records.db", DAILY_DB)

conn = sqlite3.connect(DAILY_DB)
placeholders = ",".join("?" * len(ORDER_IDS))
rows = conn.execute(
    f"SELECT order_no, pay_center_order_no, order_amount, pay_channel, status, user_id, create_time, update_time "
    f"FROM deposits WHERE order_no IN ({placeholders})",
    ORDER_IDS,
).fetchall()
conn.close()

found_by_order_no = {}
for order_no, pay_center_order_no, order_amount, pay_channel, status, user_id, create_time, update_time in rows:
    found_by_order_no[order_no] = {
        "order_no": order_no,
        "pay_center_order_no": pay_center_order_no,
        "amount": order_amount,
        "channel": pay_channel,
        "status": status,
        "user_id": user_id,
        "create_time": create_time,
        "update_time": update_time,
    }

result = []
for oid in ORDER_IDS:
    if oid in found_by_order_no:
        result.append({"order_id": oid, "found": True, **found_by_order_no[oid]})
    else:
        result.append({"order_id": oid, "found": False})

print("=== MATCH_RESULT_JSON_START ===")
print(json.dumps(result))
print("=== MATCH_RESULT_JSON_END ===")
print("FOUND:", sum(1 for r in result if r["found"]), "of", len(result))
