import subprocess
import sys
from datetime import datetime


SCRIPTS_TO_RUN = [
    ["integrations/ebay_sync_buyer_purchases.py"],
    ["integrations/easypost_sync_shipments.py", "--limit", "500"],
    ["integrations/ebay_sync_supplier_returns.py"],
    ["integrations/sync_revseller_sheet.py"],
    ["integrations/amazon_sync_fba_inventory.py"],
    ["integrations/amazon_sync_listing_status.py", "--active-only"],
    ["integrations/amazon_sync_inventory_planning.py"],
    ["integrations/amazon_sync_finance_balances.py", "--apply"],
    ["integrations/informed_sync_reports.py", "--write"],
    ["integrations/ynab_sync_cash_balance.py", "--apply"],
    [
        "integrations/keepa_sync_products.py",
        "--source",
        "amazon_active",
        "--limit",
        "10",
        "--batch-size",
        "10",
        "--stale-days",
        "7",
        "--min-tokens",
        "100",
        "--offers",
        "20",
        "--stock",
        "--no-history",
        "--write",
    ],
    ["integrations/business_value_snapshot.py", "--apply"],
]


def run_script(command):
    print(f"\n--- Running {' '.join(command)} ---")

    result = subprocess.run(
        [sys.executable, *command],
        capture_output=False,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{' '.join(command)} failed with exit code {result.returncode}"
        )


def main():
    print("Starting all syncs...")
    print(datetime.now())

    failures = []
    for command in SCRIPTS_TO_RUN:
        try:
            run_script(command)
        except RuntimeError as error:
            failures.append(str(error))
            print(f"ERROR: {error}")

    if failures:
        print("\nSyncs completed with failures:")
        for failure in failures:
            print(f"- {failure}")
        print(datetime.now())
        return 1

    print("\nAll syncs completed successfully.")
    print(datetime.now())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
