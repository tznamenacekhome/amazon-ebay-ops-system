"""Royal supplier history import. Default is offline parse/validation; --apply writes."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from wholesale_repository import WholesaleRepository
from wholesale_royal import parse_price_list


def get_repository(expected_project_ref: str) -> WholesaleRepository:
    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv(".env")
    load_dotenv(".env.local")
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    host = urlparse(url).hostname
    expected = (host in {"localhost", "127.0.0.1"} if expected_project_ref == "local"
                else host == f"{expected_project_ref}.supabase.co")
    if not url or not key or not expected:
        raise ValueError("Set SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY and verify --expected-project-ref")
    return WholesaleRepository(create_client(url, key))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", type=Path)
    parser.add_argument("--effective-date", help="Supplier date YYYY-MM-DD, required if document date is absent")
    parser.add_argument("--apply", action="store_true", help="Persist the parsed source and accepted observations")
    parser.add_argument("--expected-project-ref", help="Verified Supabase project reference, or local for loopback")
    parser.add_argument("--replaces-import-id", type=UUID, help="Latest completed import for an intentional same-date correction")
    parser.add_argument("--json-output", type=Path, help="Write full source-row audit, warnings and execution result locally")
    args = parser.parse_args(argv)
    if args.apply and not args.expected_project_ref:
        parser.error("--apply requires --expected-project-ref")
    try:
        payload = parse_price_list(args.workbook, args.effective_date)
        result = None
        if args.apply:
            result = get_repository(args.expected_project_ref).apply_import(
                payload, str(args.replaces_import_id) if args.replaces_import_id else None)
        summary = payload["summary"]
        print(f"Royal Electronics, Inc. - {payload['effective_date']} - USD")
        print(f"Mode: {'apply' if args.apply else 'offline preview'}; status: {payload['status']}")
        for label, key in (("Rows encountered", "rows_encountered"), ("Used skipped", "used_rows_skipped"),
                           ("Non-product rows skipped", "non_product_rows_skipped"),
                           ("Invalid rows skipped", "invalid_rows_skipped"),
                           ("Duplicate rows skipped", "duplicate_rows_skipped"),
                           ("Conflicting rows quarantined", "conflict_rows_skipped"),
                           ("Accepted products", "products_accepted"),
                           ("Identifier warnings", "identifier_warnings"), ("Warnings", "warnings"),
                           ("Errors", "errors")):
            print(f"{label}: {summary[key]}")
        if result:
            print(f"Import ID: {result['import_id']}; already imported: {result['already_imported']}")
            print(f"Products created this run: {result['products_created']}")
            print(f"Products matched existing this run: {result['products_matched']}")
            print(f"Observations created this run: {result['observations_created']}")
        else:
            print("Database not contacted; created/matched counts require --apply.")
        for error in payload["errors"][:10]:
            print(f"ERROR: {json.dumps(error, ensure_ascii=True)}", file=sys.stderr)
        if args.json_output:
            args.json_output.parent.mkdir(parents=True, exist_ok=True)
            args.json_output.write_text(json.dumps({"parsed": payload, "result": result},
                                                  ensure_ascii=False, indent=2), encoding="utf-8")
        return 2 if payload["status"] == "rejected" else 0
    except Exception as exc:
        # Do not dump credentials, HTTP headers or raw third-party exception payloads.
        print(f"Royal import failed ({type(exc).__name__}). "
              "No partial list is committed. Check the input/date, target and migration; "
              "same-date corrections require --replaces-import-id.", file=sys.stderr)
        if isinstance(exc, (ValueError, FileNotFoundError)):
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
