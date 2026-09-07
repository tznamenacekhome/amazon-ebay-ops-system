"""Read-only production check for inherited diagnostics and streamed output."""
import subprocess
import sys
import time
from sourcing_common import get_supabase_client

print("CATALOG_LOGGING_CHECK child started", flush=True)
response = get_supabase_client().table("sourcing_runs").select("sourcing_run_id").limit(1).execute()
print("CATALOG_LOGGING_CHECK tiny database read succeeded", flush=True)
result = subprocess.run([sys.executable, "-u", "-c",
                         "import os; print('CATALOG_LOGGING_CHECK grandchild before abrupt exit',flush=True); os._exit(9)"])
if result.returncode != 9:
    raise RuntimeError("Unexpected logging probe grandchild exit code")
print("CATALOG_LOGGING_CHECK abrupt grandchild exit observed: 9", flush=True)
time.sleep(17)  # Prove periodic heartbeat delivery in the production image.
print("CATALOG_LOGGING_CHECK complete", flush=True)
