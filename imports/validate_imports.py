import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

tables = [
    "purchases",
    "purchase_items",
    "supplier_returns",
    "inventory_locations",
    "import_batches"
]

for table in tables:
    result = supabase.table(table).select("*", count="exact").limit(1).execute()
    print(f"{table}: {result.count} rows")