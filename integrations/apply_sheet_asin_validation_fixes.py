import argparse
import itertools
import re
import sys
from decimal import Decimal

from dotenv import load_dotenv

try:
    from validate_asins_against_purchase_sheet import (
        EXCLUDED_STATUSES,
        build_validation_rows,
        get_supabase_client,
        load_mbop_orders,
        load_sheet_orders,
        normalize_asin,
        normalize_order_number,
        normalize_text,
        parse_qty,
    )
except ImportError:
    from integrations.validate_asins_against_purchase_sheet import (
        EXCLUDED_STATUSES,
        build_validation_rows,
        get_supabase_client,
        load_mbop_orders,
        load_sheet_orders,
        normalize_asin,
        normalize_order_number,
        normalize_text,
        parse_qty,
    )


def title_tokens(value):
    text = normalize_text(value).lower()
    return {
        token
        for token in re.split(r"[^a-z0-9]+", text)
        if len(token) > 1
    }


def title_score(item, target):
    item_title = normalize_text(item.get("amazon_title") or item.get("title"))
    target_title = normalize_text(target["title"])
    item_tokens = title_tokens(item_title)
    target_tokens = title_tokens(target_title)

    if not item_tokens or not target_tokens:
        return 0

    overlap = len(item_tokens & target_tokens)
    union = len(item_tokens | target_tokens)
    return (overlap * 100) + int((overlap / union) * 100)


def active_items_for_order(raw_items, order_number):
    items = []

    for item in raw_items:
        purchase = item.get("purchases") or {}
        item_order_number = normalize_order_number(purchase.get("supplier_order_id"))

        if item_order_number != order_number:
            continue

        status = normalize_text(item.get("current_status")).lower()
        if item.get("exclude_from_purchase_reporting") or status in EXCLUDED_STATUSES:
            continue

        items.append(item)

    return items


def sheet_targets_for_order(sheet_order):
    targets = []

    for asin, qty in sheet_order["asin_qty"].items():
        titles = sheet_order["titles_by_asin"].get(asin, [])
        targets.append({
            "asin": asin,
            "quantity": int(qty),
            "title": titles[0] if titles else "",
        })

    return targets


def item_needs_update(item, target):
    return normalize_asin(item.get("asin")) != target["asin"]


def choose_assignment(items, targets):
    if not items or not targets:
        return [], "no_assignment"

    if len(items) != len(targets):
        return [], "item_target_count_mismatch"

    best_assignment = None
    best_score = None

    for permutation in itertools.permutations(targets):
        score = 0

        for item, target in zip(items, permutation):
            item_qty = parse_qty(item.get("quantity"))

            if item_qty != target["quantity"]:
                score -= 10_000

            score += title_score(item, target)

            if normalize_asin(item.get("asin")) == target["asin"]:
                score += 1_000

        if best_score is None or score > best_score:
            best_score = score
            best_assignment = list(zip(items, permutation))

    return best_assignment or [], "title_quantity_assignment"


def build_updates(sheet_orders, raw_items, validation_rows):
    issue_orders = {
        row["order_number"]
        for row in validation_rows
        if row.get("issue_type") != "mbop_order_not_in_sheet"
    }
    updates = []
    skipped = []

    for order_number in sorted(issue_orders):
        sheet_order = sheet_orders.get(order_number)
        if not sheet_order:
            skipped.append({
                "order_number": order_number,
                "reason": "no_sheet_order",
            })
            continue

        items = active_items_for_order(raw_items, order_number)
        targets = sheet_targets_for_order(sheet_order)
        assignment, method = choose_assignment(items, targets)

        if not assignment:
            skipped.append({
                "order_number": order_number,
                "reason": method,
                "item_count": len(items),
                "target_count": len(targets),
            })
            continue

        for item, target in assignment:
            if not item_needs_update(item, target):
                continue

            updates.append({
                "order_number": order_number,
                "item_id": item["item_id"],
                "old_asin": normalize_asin(item.get("asin")) or "",
                "new_asin": target["asin"],
                "old_amazon_title": normalize_text(item.get("amazon_title")),
                "new_amazon_title": target["title"],
                "quantity": parse_qty(item.get("quantity")),
                "method": method,
            })

    return updates, skipped


def apply_updates(supabase, updates):
    for update in updates:
        payload = {
            "asin": update["new_asin"],
            "amazon_title": update["new_amazon_title"] or None,
        }

        (
            supabase.table("purchase_items")
            .update(payload)
            .eq("item_id", update["item_id"])
            .execute()
        )


def print_updates(updates, skipped):
    print("Spreadsheet ASIN correction plan")
    print("--------------------------------")
    print(f"Updates: {len(updates)}")
    print(f"Skipped orders: {len(skipped)}")
    print()

    for update in updates:
        print(
            f"{update['order_number']} | {update['item_id']} | "
            f"{update['old_asin'] or '--'} -> {update['new_asin']} | "
            f"{update['new_amazon_title']}"
        )

    if skipped:
        print()
        print("Skipped")
        print("-------")
        for row in skipped:
            print(row)


def main():
    parser = argparse.ArgumentParser(
        description="Apply ASIN corrections from the reference Purchases sheet."
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    supabase = get_supabase_client()
    sheet_orders, _ = load_sheet_orders()
    mbop_orders = load_mbop_orders(supabase)
    validation_rows, _ = build_validation_rows(sheet_orders, mbop_orders)
    raw_items = []
    offset = 0

    while True:
        response = (
            supabase.table("purchase_items")
            .select(
                "item_id,title,amazon_title,asin,quantity,current_status,"
                "exclude_from_purchase_reporting,purchases(supplier_order_id)"
            )
            .range(offset, offset + 999)
            .execute()
        )
        page = response.data or []
        raw_items.extend(page)

        if len(page) < 1000:
            break

        offset += 1000

    updates, skipped = build_updates(sheet_orders, raw_items, validation_rows)
    print_updates(updates, skipped)

    if args.apply:
        apply_updates(supabase, updates)
        print()
        print("Applied updates.")
    else:
        print()
        print("Dry run only. Re-run with --apply to update Supabase.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
