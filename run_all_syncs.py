import subprocess
import sys
from datetime import datetime

def run_script(script_path):
    print(f"\n--- Running {script_path} ---")
    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=False,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(f"{script_path} failed with exit code {result.returncode}")

def main():
    print("Starting all syncs...")
    print(datetime.now())

    run_script("integrations/ebay_sync_orders.py")

    print("\nAll syncs completed successfully.")
    print(datetime.now())

if __name__ == "__main__":
    main()