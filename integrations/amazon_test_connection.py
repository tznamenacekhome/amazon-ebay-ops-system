"""Smoke-test Amazon SP-API credentials without reading restricted PII.

The script first validates Login with Amazon token exchange, then attempts a
read-only FBA inventory summary call when AWS SigV4 credentials are present.
It does not write to Supabase and does not call Amazon orders, buyer, address,
or other restricted-data operations.
"""

from __future__ import annotations

import argparse
import logging
import sys

from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError


def main() -> int:
    parser = argparse.ArgumentParser(description="Test MBOP Amazon SP-API auth")
    parser.add_argument(
        "--auth-only",
        action="store_true",
        help="Only test Login with Amazon token exchange.",
    )
    parser.add_argument(
        "--limit-log",
        type=int,
        default=5,
        help="Number of returned inventory SKUs to mention in logs.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    try:
        client = AmazonSPAPIClient.from_env()
        token_result = client.test_lwa_access_token()
        logging.info(
            "LWA token exchange succeeded; expires_at=%s",
            token_result.get("expires_at"),
        )

        if args.auth_only:
            logging.info("Auth-only mode complete; no SP-API resource call made.")
            return 0

        missing_sigv4 = client.config.missing_sigv4_fields()
        if missing_sigv4:
            logging.warning(
                "Skipping SP-API resource call because SigV4 credentials are missing: %s",
                ", ".join(missing_sigv4),
            )
            logging.warning(
                "Add AWS signing credentials before testing inventory/listing/pricing reads."
            )
            return 2

        payload = client.get_inventory_summaries(details=False)
        summaries = (
            payload.get("payload", {}).get("inventorySummaries")
            if isinstance(payload, dict)
            else None
        ) or []
        logging.info(
            "FBA inventory summary call succeeded; summaries_returned=%s",
            len(summaries),
        )
        for summary in summaries[: max(args.limit_log, 0)]:
            logging.info(
                "Inventory summary SKU=%s ASIN=%s",
                summary.get("sellerSku"),
                summary.get("asin"),
            )

        return 0
    except AmazonSPAPIError as error:
        logging.error("Amazon SP-API test failed safely: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - top-level smoke test guard
        logging.exception("Unexpected Amazon SP-API test failure: %s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
