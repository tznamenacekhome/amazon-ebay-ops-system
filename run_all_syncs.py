import subprocess
import sys
from datetime import datetime


SCRIPTS_TO_RUN = [
    ["integrations/ebay_sync_buyer_purchases.py"],
    ["integrations/easypost_sync_shipments.py", "--limit", "500"],
    ["integrations/ebay_sync_supplier_returns.py"],
    ["integrations/sync_revseller_sheet.py"],
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

    for command in SCRIPTS_TO_RUN:
        run_script(command)

    print("\nAll syncs completed successfully.")
    print(datetime.now())


if __name__ == "__main__":
    main()
