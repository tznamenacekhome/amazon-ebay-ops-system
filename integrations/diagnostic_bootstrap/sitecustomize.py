"""Inherited by catalog children and grandchildren through PYTHONPATH."""
import os

if os.getenv("MBOP_CATALOG_DIAGNOSTICS") == "1":
    try:
        from scheduler_diagnostics import install
        install()
    except Exception as error:
        # Diagnostic failure is visible, but must not prevent operational work.
        print("CATALOG_DIAGNOSTIC_INIT_ERROR " + type(error).__name__, flush=True)
