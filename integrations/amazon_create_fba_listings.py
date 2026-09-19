"""Create narrowly scoped FBA offers for received MBOP inventory.

The command is plan-only unless ``--preview`` or ``--write`` is supplied.
``--write`` is intentionally required to enable PUT calls in the shared SP-API
client. Listings are created with zero merchant-fulfilled inventory and the
Amazon North America fulfillment channel.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from amazon_check_listing_restrictions import classify_restriction_payload
from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError
from sourcing_common import get_supabase_client


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = parse_args()
    asins = unique_asins(args.asin)
    if not asins:
        raise SystemExit("At least one --asin is required.")

    supabase = get_supabase_client()
    queue_rows = fetch_queue_rows(supabase, asins)
    missing = [asin for asin in asins if asin not in queue_rows]
    if missing:
        raise SystemExit(
            "ASINs are not eligible received items in the Send to Amazon queue: "
            + ", ".join(missing)
        )

    client = AmazonSPAPIClient.from_env(
        allow_listing_writes=bool(args.preview or args.write)
    )
    marketplace_id = client.config.marketplace_id
    plans = [
        build_plan(
            asin=asin,
            title=queue_rows[asin]["title"],
            price=queue_rows[asin]["price"],
            units=queue_rows[asin]["units"],
            marketplace_id=marketplace_id,
        )
        for asin in asins
    ]

    results: list[dict[str, Any]] = []
    for plan in plans:
        restriction = classify_restriction_payload(
            plan["asin"],
            client.get_listings_restrictions(
                plan["asin"], condition_type="new_new", reason_locale="en_US"
            ),
        )
        result = {
            **plan,
            "restriction_status": restriction.status,
            "restriction_messages": restriction.messages,
            "preview": None,
            "submission": None,
            "fba_conversion_preview": None,
            "fba_conversion_submission": None,
        }
        if restriction.status != "sellable":
            results.append(result)
            continue

        if args.preview or args.write:
            result["preview"] = client.put_listing_item(
                plan["seller_sku"],
                product_type="PRODUCT",
                attributes=plan["attributes"],
                mode="VALIDATION_PREVIEW",
            )
        if args.write and submission_accepted(result["preview"]):
            result["submission"] = client.put_listing_item(
                plan["seller_sku"],
                product_type="PRODUCT",
                attributes=plan["attributes"],
            )
        if args.write and submission_accepted(result["submission"]):
            catalog_attributes = (
                client.get_catalog_item(
                    plan["asin"], included_data=["attributes"]
                ).get("attributes")
                or {}
            )
            patches = build_fba_conversion_patches(catalog_attributes)
            result["fba_conversion_preview"] = client.patch_listing_item(
                plan["seller_sku"],
                product_type="PRODUCT",
                patches=patches,
                mode="VALIDATION_PREVIEW",
            )
            if submission_accepted(result["fba_conversion_preview"]):
                result["fba_conversion_submission"] = client.patch_listing_item(
                    plan["seller_sku"],
                    product_type="PRODUCT",
                    patches=patches,
                )
        results.append(result)

    artifact = write_artifact(results, mode="write" if args.write else "preview" if args.preview else "plan")
    print_summary(results, artifact)

    blocked = [row for row in results if row["restriction_status"] != "sellable"]
    invalid = [
        row
        for row in results
        if (args.preview or args.write) and not submission_accepted(row["preview"])
    ]
    failed = [
        row
        for row in results
        if args.write
        and (
            not submission_accepted(row["submission"])
            or not submission_accepted(row["fba_conversion_preview"])
            or not submission_accepted(row["fba_conversion_submission"])
        )
    ]
    return 1 if blocked or invalid or failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create FBA Listings Items offers for explicit Send to Amazon ASINs."
    )
    parser.add_argument("--asin", action="append", default=[])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true")
    mode.add_argument("--write", action="store_true")
    return parser.parse_args()


def unique_asins(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        asin = str(value or "").strip().upper()
        if len(asin) == 10 and asin not in output:
            output.append(asin)
    return output


def fetch_queue_rows(supabase: Any, asins: list[str]) -> dict[str, dict[str, Any]]:
    response = (
        supabase.table("purchase_items")
        .select(
            "asin,amazon_title,title,quantity,target_price,current_status," 
            "marketplace,exclude_from_purchase_reporting"
        )
        .in_("asin", asins)
        .eq("current_status", "received")
        .execute()
    )
    grouped: dict[str, dict[str, Any]] = {}
    for row in response.data or []:
        if row.get("exclude_from_purchase_reporting") is True:
            continue
        if row.get("marketplace") == "eBay":
            continue
        asin = str(row.get("asin") or "").strip().upper()
        price = money(row.get("target_price"))
        quantity = int(row.get("quantity") or 0)
        if not asin or price is None or quantity <= 0:
            continue
        current = grouped.setdefault(
            asin,
            {
                "title": row.get("amazon_title") or row.get("title") or asin,
                "price": price,
                "units": 0,
            },
        )
        current["price"] = max(current["price"], price)
        current["units"] += quantity
    return grouped


def build_plan(
    *,
    asin: str,
    title: str,
    price: Decimal,
    units: int,
    marketplace_id: str,
) -> dict[str, Any]:
    seller_sku = f"MBOP-{asin}-NEW"
    return {
        "asin": asin,
        "seller_sku": seller_sku,
        "title": title,
        "price": float(price),
        "units": units,
        "attributes": {
            "condition_type": [
                {"value": "new_new", "marketplace_id": marketplace_id}
            ],
            "merchant_suggested_asin": [
                {"value": asin, "marketplace_id": marketplace_id}
            ],
            "batteries_required": [
                {"value": False, "marketplace_id": marketplace_id}
            ],
            "supplier_declared_dg_hz_regulation": [
                {"value": "not_applicable", "marketplace_id": marketplace_id}
            ],
            "purchasable_offer": [
                {
                    "currency": "USD",
                    "our_price": [
                        {"schedule": [{"value_with_tax": float(price)}]}
                    ],
                    "marketplace_id": marketplace_id,
                }
            ],
            "fulfillment_availability": [
                {
                    "fulfillment_channel_code": "AMAZON_NA",
                }
            ],
        },
    }


def money(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except Exception:
        return None
    return amount if amount >= 0 else None


def build_fba_conversion_patches(
    catalog_attributes: dict[str, Any],
) -> list[dict[str, Any]]:
    required = (
        "batteries_required",
        "item_package_dimensions",
        "item_package_weight",
    )
    missing = [name for name in required if not catalog_attributes.get(name)]
    if missing:
        raise AmazonSPAPIError(
            "Amazon catalog is missing attributes required for FBA conversion: "
            + ", ".join(missing)
        )
    return [
        {
            "op": "add",
            "path": "/attributes/fulfillment_availability",
            "value": [{"fulfillment_channel_code": "AMAZON_NA"}],
        },
        {
            "op": "delete",
            "path": "/attributes/fulfillment_availability",
            "value": [{"fulfillment_channel_code": "DEFAULT"}],
        },
        *[
            {
                "op": "replace",
                "path": f"/attributes/{name}",
                "value": catalog_attributes[name],
            }
            for name in required
        ],
    ]


def submission_accepted(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("status") in {"VALID", "ACCEPTED"}


def write_artifact(results: list[dict[str, Any]], *, mode: str) -> Path:
    path = ROOT / "tmp" / f"amazon_create_fba_listings_{mode}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    return path


def print_summary(results: list[dict[str, Any]], artifact: Path) -> None:
    print("Amazon FBA listing creation")
    print("---------------------------")
    for row in results:
        preview = row.get("preview") or {}
        submission = row.get("submission") or {}
        conversion = row.get("fba_conversion_submission") or {}
        print(
            f"{row['asin']} | {row['seller_sku']} | ${row['price']:.2f} | "
            f"restriction={row['restriction_status']} | "
            f"preview={preview.get('status', '--')} | "
            f"submission={submission.get('status', '--')} | "
            f"fba_conversion={conversion.get('status', '--')}"
        )
        for issue in (
            preview.get("issues")
            or submission.get("issues")
            or (row.get("fba_conversion_preview") or {}).get("issues")
            or conversion.get("issues")
            or []
        ):
            print(
                f"  - {issue.get('severity', 'UNKNOWN')}: "
                f"{issue.get('code', '--')} {issue.get('message', '')}"
            )
    print(f"Artifact: {artifact}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AmazonSPAPIError as error:
        raise SystemExit(str(error)) from error
