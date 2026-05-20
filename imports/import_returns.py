import os
import json
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client


RETURNS_CSV = "data/returns.csv"


def clean_column_name(name):
    return str(name).strip().replace("\ufeff", "")


def clean_text(value):
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def clean_money(value):
    if pd.isna(value):
        return None
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def clean_date(value):
    if pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def main():
    print("Starting corrected returns import...")

    load_dotenv()

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    )

    df = pd.read_csv(RETURNS_CSV, dtype=str)
    df.columns = [clean_column_name(col) for col in df.columns]
    df = df.loc[:, ~df.columns.str.contains("^Unnamed", case=False, na=False)]

    print(f"Rows found: {len(df)}")
    print("Columns found:")
    print(list(df.columns))

    batch_result = supabase.table("import_batches").insert({
        "source_name": "ebay purchases - Returns.csv",
        "notes": "Corrected supplier returns import using actual CSV column names"
    }).execute()

    import_batch_id = batch_result.data[0]["import_batch_id"]
    print(f"Created import batch: {import_batch_id}")

    inserted_count = 0
    linked_count = 0
    skipped_count = 0

    for index, row in df.iterrows():
        source_row_number = index + 2

        order_number = clean_text(row.get("Order ID"))
        asin = clean_text(row.get("ASIN"))
        title = clean_text(row.get("Title"))
        supplier = clean_text(row.get("Source")) or "eBay"
        date_opened = clean_date(row.get("Date opened"))
        date_sent = clean_date(row.get("Date Sent"))
        refund_expected = clean_money(row.get("Total Price")) or clean_money(row.get("Price Paid"))

        if not title and not asin and not order_number:
            skipped_count += 1
            continue

        raw_json = json.loads(row.to_json())

        matching_item_id = None

        if order_number:
            purchase_match = (
                supabase.table("purchases")
                .select("purchase_id")
                .eq("supplier_order_id", order_number)
                .limit(1)
                .execute()
            )

            if purchase_match.data:
                purchase_id = purchase_match.data[0]["purchase_id"]

                item_match = (
                    supabase.table("purchase_items")
                    .select("item_id")
                    .eq("purchase_id", purchase_id)
                    .limit(1)
                    .execute()
                )

                if item_match.data:
                    matching_item_id = item_match.data[0]["item_id"]
                    linked_count += 1

        payload = {
            "item_id": matching_item_id,
            "supplier": supplier,
            "supplier_order_id": order_number,
            "return_reason": None,
            "seller_fault": None,
            "buyer_fault": None,
            "partial_refund": False,
            "refund_expected": refund_expected,
            "opened_date": date_opened,
            "shipped_date": date_sent,
            "refund_verified": False,
            "notes": f"Imported from corrected returns CSV row {source_row_number}",
        }

        supabase.table("supplier_returns").insert(payload).execute()
        inserted_count += 1

        if inserted_count % 50 == 0:
            print(f"Inserted {inserted_count} return rows...")

    print("Corrected returns import complete.")
    print(f"Inserted rows: {inserted_count}")
    print(f"Linked to purchase_items: {linked_count}")
    print(f"Skipped rows: {skipped_count}")


if __name__ == "__main__":
    main()