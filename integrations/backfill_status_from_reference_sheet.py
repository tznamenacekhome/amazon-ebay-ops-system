import argparse
import itertools
import os
import re
import sys
from collections import Counter, defaultdict

import gspread
from dotenv import load_dotenv
from supabase import create_client


REFERENCE_SHEET_ID = "1K0-G3BJ-dKLA3U3VYGiPD1kVMoQxyBKQzZfx8NKzrcA"
REFERENCE_WORKSHEET = "status"
PAGE_SIZE = 1000
EXCLUDED_STATUSES = {"cancelled", "return_opened"}
BLANK_MARKERS = {"", "N/A", "NA", "NONE", "NULL", "-", "--"}


def normalize_header(value):
    return str(value or "").replace("\xa0", " ").strip().lower()


def normalize_text(value):
    return str(value or "").replace("\xa0", " ").strip()


def normalize_order_number(value):
    text = normalize_text(value)
    return "" if text.upper() in BLANK_MARKERS else text


def normalize_asin(value):
    text = normalize_text(value).upper()
    return None if text in BLANK_MARKERS else text


def normalize_sheet_status(value):
    text = normalize_text(value).lower().replace("-", " ")

    if text == "listed":
        return "listed"

    if text == "received":
        return "received"

    if not text:
        return None

    raise ValueError(f"Unsupported status value: {value!r}")


def parse_qty(value):
    try:
        parsed = int(float(str(value or "").replace(",", "").strip()))
        return parsed if parsed > 0 else 1
    except Exception:
        return 1


def get_gspread_client():
    return gspread.service_account(filename=os.environ["GOOGLE_APPLICATION_CREDENTIALS"])


def get_supabase_client():
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )


def load_status_targets():
    worksheet = (
        get_gspread_client()
        .open_by_key(REFERENCE_SHEET_ID)
        .worksheet(REFERENCE_WORKSHEET)
    )
    values = worksheet.get_all_values()

    if not values:
        return {}, Counter()

    headers = [normalize_header(value) for value in values[0]]
    header_index = {header: index for index, header in enumerate(headers)}
    required = {"asin", "order number", "qty", "title", "status"}
    missing = required - set(header_index)

    if missing:
        raise RuntimeError(f"Status sheet missing columns: {sorted(missing)}")

    targets = defaultdict(list)
    stats = Counter()

    for row in values[1:]:
        stats["rows_scanned"] += 1
        order_number = normalize_order_number(row[header_index["order number"]])
        asin = normalize_asin(row[header_index["asin"]])

        if not order_number:
            stats["rows_without_order"] += 1
            continue

        if not asin:
            stats["rows_without_asin"] += 1
            continue

        status = normalize_sheet_status(row[header_index["status"]])
        qty = parse_qty(row[header_index["qty"]])
        title = normalize_text(row[header_index["title"]])

        if status is None:
            stats["blank_status_rows"] += 1
            stats["blank_status_units"] += qty
            continue

        targets[(order_number, asin)].append({
            "order_number": order_number,
            "asin": asin,
            "quantity": qty,
            "status": status,
            "title": title,
        })
        stats[f"target_{status}"] += qty

    return targets, stats


def fetch_purchase_items(supabase):
    rows = []
    offset = 0

    while True:
        response = (
            supabase.table("purchase_items")
            .select(
                "item_id,purchase_id,title,amazon_title,asin,quantity,current_status,"
                "target_price,unit_cost,system,tracking_number,condition,"
                "supplier_listing_url,import_batch_id,raw_import_json,"
                "manual_title_override,manual_unit_cost_override,manual_split_child,"
                "manual_split_parent_item_id,marketplace,received_date,"
                "exclude_from_purchase_reporting,purchases(supplier_order_id)"
            )
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        page = response.data or []
        rows.extend(page)

        if len(page) < PAGE_SIZE:
            break

        offset += PAGE_SIZE

    return rows


def active_item_groups(items):
    groups = defaultdict(list)

    for item in items:
        purchase = item.get("purchases") or {}
        order_number = normalize_order_number(purchase.get("supplier_order_id"))
        asin = normalize_asin(item.get("asin"))
        status = normalize_text(item.get("current_status")).lower()

        if not order_number or not asin:
            continue

        if item.get("exclude_from_purchase_reporting") or status in EXCLUDED_STATUSES:
            continue

        groups[(order_number, asin)].append(item)

    return groups


def title_tokens(value):
    return {
        token
        for token in re.split(r"[^a-z0-9]+", normalize_text(value).lower())
        if len(token) > 1
    }


def title_score(item, target):
    item_title = normalize_text(item.get("amazon_title") or item.get("title"))
    item_tokens = title_tokens(item_title)
    target_tokens = title_tokens(target["title"])

    if not item_tokens or not target_tokens:
        return 0

    overlap = len(item_tokens & target_tokens)
    union = len(item_tokens | target_tokens)
    return (overlap * 100) + int((overlap / union) * 100)


def expand_targets(targets):
    expanded = []

    for target in targets:
        for _ in range(target["quantity"]):
            expanded.append({**target, "quantity": 1})

    return expanded


def expand_items(items):
    expanded = []

    for item in items:
        quantity = parse_qty(item.get("quantity"))
        if quantity == 1:
            expanded.append(item)
            continue

        for copy_index in range(quantity):
            expanded.append({**item, "_copy_index": copy_index, "quantity": 1})

    return expanded


def choose_assignment(items, targets):
    expanded_items = expand_items(items)
    expanded_targets = expand_targets(targets)

    if len(expanded_items) != len(expanded_targets):
        return [], "quantity_mismatch"

    best_assignment = None
    best_score = None

    for permutation in itertools.permutations(expanded_targets):
        score = 0

        for item, target in zip(expanded_items, permutation):
            score += title_score(item, target)

            if normalize_text(item.get("current_status")).lower() == target["status"]:
                score += 1000

        if best_score is None or score > best_score:
            best_score = score
            best_assignment = list(zip(expanded_items, permutation))

    return best_assignment or [], "title_status_assignment"


def build_actions(groups, targets_by_key):
    actions = []
    skipped = []

    for key, targets in sorted(targets_by_key.items()):
        items = groups.get(key, [])

        if not items:
            skipped.append({"key": key, "reason": "no_mbop_item"})
            continue

        target_statuses = {target["status"] for target in targets}

        if len(target_statuses) == 1:
            target_status = next(iter(target_statuses))

            for item in items:
                current_status = normalize_text(item.get("current_status")).lower()

                if current_status == target_status:
                    continue

                actions.append({
                    "action": "update",
                    "item_id": item["item_id"],
                    "updates": {"current_status": target_status},
                    "old_status": current_status,
                    "new_status": target_status,
                    "method": "single_status_group",
                })

            continue

        assignment, method = choose_assignment(items, targets)

        if not assignment:
            skipped.append({"key": key, "reason": method})
            continue

        source_instance_counts = Counter(item["item_id"] for item, _ in assignment)

        for item, target in assignment:
            current_status = normalize_text(item.get("current_status")).lower()
            item_id = item["item_id"]
            needs_split = source_instance_counts[item_id] > 1
            copy_index = item.get("_copy_index", 0)

            if needs_split and copy_index > 0:
                actions.append({
                    "action": "split_insert",
                    "item": item,
                    "status": target["status"],
                    "method": method,
                })
                continue

            updates = {}

            if needs_split and parse_qty(item.get("quantity")) != 1:
                updates["quantity"] = 1

            if current_status != target["status"]:
                updates["current_status"] = target["status"]

            if updates:
                actions.append({
                    "action": "update",
                    "item_id": item_id,
                    "updates": updates,
                    "old_status": current_status,
                    "new_status": target["status"],
                    "method": method,
                })

    return actions, skipped


def split_payload(item, status):
    return {
        "purchase_id": item["purchase_id"],
        "title": item.get("title"),
        "amazon_title": item.get("amazon_title"),
        "quantity": 1,
        "unit_cost": item.get("unit_cost"),
        "asin": item.get("asin"),
        "target_price": item.get("target_price"),
        "system": item.get("system"),
        "tracking_number": item.get("tracking_number"),
        "current_status": status,
        "condition": item.get("condition"),
        "supplier_listing_url": item.get("supplier_listing_url"),
        "import_batch_id": item.get("import_batch_id"),
        "raw_import_json": item.get("raw_import_json"),
        "manual_title_override": bool(item.get("manual_title_override")),
        "manual_unit_cost_override": bool(item.get("manual_unit_cost_override")),
        "manual_split_child": True,
        "manual_split_parent_item_id": item["item_id"],
        "marketplace": item.get("marketplace"),
        "received_date": item.get("received_date"),
    }


def link_split_item_to_shipments(supabase, item_id, purchase_id):
    shipments = (
        supabase.table("inbound_shipments")
        .select("inbound_shipment_id")
        .eq("purchase_id", purchase_id)
        .execute()
        .data
        or []
    )

    for shipment in shipments:
        supabase.table("inbound_shipment_items").insert({
            "inbound_shipment_id": shipment["inbound_shipment_id"],
            "item_id": item_id,
            "quantity_expected_in_package": 1,
            "quantity_received_from_package": None,
            "received_verified": False,
            "notes": "Linked from one-time status backfill split",
        }).execute()


def apply_actions(supabase, actions):
    applied = Counter()
    status_only_updates = defaultdict(list)
    other_updates = []
    split_actions = []

    for action in actions:
        if action["action"] == "update" and set(action["updates"].keys()) == {"current_status"}:
            status_only_updates[action["updates"]["current_status"]].append(
                action["item_id"]
            )
            continue

        if action["action"] == "update":
            other_updates.append(action)
            continue

        if action["action"] == "split_insert":
            split_actions.append(action)

    for status, item_ids in status_only_updates.items():
        for index in range(0, len(item_ids), 500):
            chunk = item_ids[index:index + 500]
            (
                supabase.table("purchase_items")
                .update({"current_status": status})
                .in_("item_id", chunk)
                .execute()
            )
            applied["updated"] += len(chunk)

    for action in other_updates:
        (
            supabase.table("purchase_items")
            .update(action["updates"])
            .eq("item_id", action["item_id"])
            .execute()
        )
        applied["updated"] += 1

    for action in split_actions:
        payload = split_payload(action["item"], action["status"])
        result = (
            supabase.table("purchase_items")
            .insert(payload)
            .execute()
        )
        new_item = result.data[0]
        link_split_item_to_shipments(
            supabase,
            new_item["item_id"],
            action["item"]["purchase_id"],
        )
        applied["split_inserted"] += 1

    return applied


def print_plan(actions, skipped, stats):
    action_counts = Counter(action["action"] for action in actions)
    status_counts = Counter()

    for action in actions:
        status = action.get("new_status") or action.get("status")
        status_counts[status] += 1

    print("Reference status backfill")
    print("-------------------------")
    print(f"Rows scanned: {stats['rows_scanned']}")
    print(f"Rows without order: {stats['rows_without_order']}")
    print(f"Rows without ASIN: {stats['rows_without_asin']}")
    print(f"Blank status rows skipped: {stats['blank_status_rows']}")
    print(f"Blank status units skipped: {stats['blank_status_units']}")
    print(f"Actions: {len(actions)}")
    print(f"Skipped groups: {len(skipped)}")
    print()
    print("Actions by type")
    for key, value in sorted(action_counts.items()):
        print(f"{key}: {value}")
    print()
    print("Actions by status")
    for key, value in sorted(status_counts.items()):
        print(f"{key}: {value}")

    if skipped:
        print()
        print("Skipped")
        for row in skipped:
            print(row)


def main():
    parser = argparse.ArgumentParser(
        description="One-time backfill of MBOP item statuses from the reference status sheet."
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    supabase = get_supabase_client()
    targets, stats = load_status_targets()
    items = fetch_purchase_items(supabase)
    groups = active_item_groups(items)
    actions, skipped = build_actions(groups, targets)

    print_plan(actions, skipped, stats)

    if args.apply:
        applied = apply_actions(supabase, actions)
        print()
        print("Applied")
        for key, value in sorted(applied.items()):
            print(f"{key}: {value}")
    else:
        print()
        print("Dry run only. Re-run with --apply to update Supabase.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
