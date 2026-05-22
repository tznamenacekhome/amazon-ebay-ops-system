import subprocess
import sys
from datetime import datetime


SCRIPTS_TO_RUN = [
    "integrations/ebay_sync_buyer_purchases.py",
    "integrations/ebay_sync_supplier_returns.py",
    "integrations/sync_revseller_sheet.py",
]


def run_script(script_path):
    print(f"\n--- Running {script_path} ---")

    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=False,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"{script_path} failed with exit code {result.returncode}"
        )


def main():
    print("Starting all syncs...")
    print(datetime.now())

    for script_path in SCRIPTS_TO_RUN:
        run_script(script_path)

    print("\nAll syncs completed successfully.")
    print(datetime.now())


if __name__ == "__main__":
    main()