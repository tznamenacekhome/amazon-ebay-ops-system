import os
import json
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client


PURCHASES_CSV = "data/purchases.csv"


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


def clean_int(value):
    if pd.isna(value):
        return None
    try:
        return int(float(value))
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
    print("Starting purchase import...")

    load_dotenv()

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    supabase = create_client(url, key)

    df = pd.read_csv(PURCHASES_CSV, dtype=str)
    df.columns = [clean_column_name(col) for col in df.columns]

    # Remove unnamed/blank columns
    df = df.loc[:, ~df.columns.str.contains("^Unnamed", case=False, na=False)]

    print(f"Rows found: {len(df)}")
    print("Columns found:")
    print(list(df.columns))

    batch_result = supabase.table("import_batches").insert({
        "source_name": "ebay purchases - Purchases.csv",
        "notes": "Initial historical purchase import from Google Sheets CSV"
    }).execute()

    import_batch_id = batch_result.data[0]["import_batch_id"]
    print(f"Created import batch: {import_batch_id}")

    inserted_count = 0
    skipped_count = 0

    for index, row in df.iterrows():
        source_row_number = index + 2  # CSV row plus header row

        asin = clean_text(row.get("ASIN"))
        title = clean_text(row.get("Item title")) or clean_text(row.get("Title"))
        system = clean_text(row.get("System"))
        cost = clean_money(row.get("Cost"))
        list_price = clean_money(row.get("List Price"))
        qty = clean_int(row.get("QTY")) or 1
        purchased_date = clean_date(row.get("Purchased date"))
        supplier = clean_text(row.get("Supplier")) or "eBay"
        order_number = clean_text(row.get("Order Number"))
        tracking = clean_text(row.get("Tracking"))

        if not title and not asin and not order_number:
            skipped_count += 1
            continue

        raw_json = json.loads(row.to_json())

        purchase_payload = {
            "supplier": supplier,
            "supplier_order_id": order_number,
            "order_date": purchased_date,
            "total_order_cost": cost * qty if cost is not None else None,
            "order_status": "imported",
            "import_batch_id": import_batch_id,
            "source_row_number": source_row_number,
            "raw_import_json": raw_json
        }

        purchase_result = supabase.table("purchases").insert(purchase_payload).execute()
        purchase_id = purchase_result.data[0]["purchase_id"]

        if tracking:
            current_status = "in_transit"
        else:
            current_status = "ordered"

        item_payload = {
            "purchase_id": purchase_id,
            "asin": asin,
            "title": title or "Unknown Title",
            "system": system,
            "quantity": qty,
            "unit_cost": cost,
            "target_price": list_price,
            "current_status": current_status,
            "condition": "new",
            "tracking_number": tracking,
            "supplier_listing_url": None,
            "import_batch_id": import_batch_id,
            "source_row_number": source_row_number,
            "raw_import_json": raw_json
        }

        supabase.table("purchase_items").insert(item_payload).execute()

        inserted_count += 1

        if inserted_count % 100 == 0:
            print(f"Inserted {inserted_count} rows...")

    print("Purchase import complete.")
    print(f"Inserted rows: {inserted_count}")
    print(f"Skipped rows: {skipped_count}")


if __name__ == "__main__":
    main()