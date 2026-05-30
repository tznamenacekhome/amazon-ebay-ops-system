import subprocess
import sys
from datetime import datetime
from pathlib import Path
import json


HEALTH_LOG_PATH = Path("logs/sync_health.json")


SCRIPTS_TO_RUN = [
    ["integrations/ebay_sync_buyer_purchases.py"],
    ["integrations/easypost_sync_shipments.py", "--limit", "500"],
    ["integrations/ebay_sync_supplier_returns.py"],
    ["integrations/sync_revseller_sheet.py"],
    ["integrations/amazon_sync_fba_inventory.py"],
    ["integrations/amazon_sync_listing_status.py", "--active-only"],
    ["integrations/amazon_sync_inventory_planning.py"],
    ["integrations/amazon_sync_finance_balances.py", "--apply"],
    ["integrations/inventory_reconcile.py"],
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
    started_at = datetime.now().astimezone().isoformat()
    print(f"\n--- Running {' '.join(command)} ---")

    result = subprocess.run(
        [sys.executable, *command],
        capture_output=False,
        text=True,
    )

    if result.returncode != 0:
        write_health_record(
            command=command,
            status="failed",
            started_at=started_at,
            message=f"{' '.join(command)} failed with exit code {result.returncode}",
        )
        raise RuntimeError(
            f"{' '.join(command)} failed with exit code {result.returncode}"
        )

    write_health_record(command=command, status="ok", started_at=started_at)


def write_health_record(command, status, started_at, message=None):
    HEALTH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    command_text = " ".join(command)
    finished_at = datetime.now().astimezone().isoformat()

    try:
        records = json.loads(HEALTH_LOG_PATH.read_text(encoding="utf-8"))
        if not isinstance(records, dict):
            records = {}
    except FileNotFoundError:
        records = {}
    except json.JSONDecodeError:
        records = {}

    records[command_text] = {
        "command": command_text,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "message": message,
    }

    HEALTH_LOG_PATH.write_text(
        json.dumps(records, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
