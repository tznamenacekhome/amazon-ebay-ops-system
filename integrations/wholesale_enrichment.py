"""Bounded, resumable Phase 2 wholesale Amazon enrichment worker."""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
from typing import Any

from amazon_check_listing_restrictions import classify_restriction_payload
from amazon_spapi_client import AmazonSPAPIClient, AmazonSPAPIError
from amazon_sync_catalog_items import INCLUDED_DATA, normalize_catalog_item
from sourcing_common import get_supabase_client
from wholesale_matching import (
    EVALUATOR_VERSION, evaluate_compatibility, identity_signature,
    identifier_search, merge_candidates, query_fingerprint, search_items,
    select_preferred, title_platform_query,
)
from wholesale_repository import WholesaleRepository


LOGGER = logging.getLogger("wholesale_enrichment")
SEARCH_SUCCESS_TTL = dt.timedelta(days=30)
SEARCH_EMPTY_TTL = dt.timedelta(days=7)
SEARCH_ERROR_TTL = dt.timedelta(hours=1)
CATALOG_TTL = dt.timedelta(days=30)
ELIGIBILITY_TTL = dt.timedelta(days=7)
UNKNOWN_ELIGIBILITY_TTL = dt.timedelta(hours=6)


class WholesaleEnrichmentService:
    def __init__(self, repository: WholesaleRepository, amazon: AmazonSPAPIClient,
                 *, seller_id: str, marketplace_id: str) -> None:
        if not seller_id:
            raise ValueError("Amazon seller_id is required for eligibility cache isolation")
        self.repository = repository
        self.amazon = amazon
        self.seller_id = seller_id
        self.marketplace_id = marketplace_id

    def enrich_product(self, supplier_product_id: str) -> dict[str, Any]:
        self._search_errors: list[str] = []
        product = self.repository.get_product(supplier_product_id)
        if not product:
            raise ValueError(f"Wholesale product not found: {supplier_product_id}")
        product = effective_product_identity(product)
        prior_detail = self.repository.get_matching_detail(supplier_product_id, self.marketplace_id)
        prior_state = prior_detail.get("match_state") or {}
        prior_candidates = prior_detail.get("candidates") or []
        prior_selected = next((row for row in prior_candidates if row.get("candidate_id") == prior_state.get("selected_candidate_id")), None)
        manual_asin = prior_selected.get("asin") if prior_state.get("selection_source") == "manual" and prior_selected else None
        force_search = bool(prior_state.get("rematch_requested"))

        identifier_items: list[dict] = []
        identifier = identifier_search(product.get("normalized_identifier"), product.get("identifier_type"))
        if identifier:
            value, kind = identifier
            identifier_items = self._search(product, "identifier", value, force_refresh=force_search,
                                            identifiers=[value], identifiers_type=kind)
        title_query = title_platform_query(product.get("raw_title"), product.get("raw_system"))
        title_items = self._search(product, "title_platform", title_query, force_refresh=force_search,
                                   keywords=title_query.split())
        discovered = merge_candidates(identifier_items, title_items)
        asins = [row["asin"] for row in discovered]

        snapshots = self._catalog_snapshots(asins)
        prior_sales = self.repository.prior_sale_asins(asins)
        velocities = self.repository.keepa_velocity(asins)
        candidate_rows: list[dict[str, Any]] = []
        compatible_asins: list[str] = []
        for discovered_row in discovered:
            asin = discovered_row["asin"]
            compatibility = evaluate_compatibility(product, snapshots[asin])
            if compatibility.status == "compatible":
                compatible_asins.append(asin)
            velocity = velocities.get(asin) or {}
            candidate_rows.append({
                "supplier_product_id": supplier_product_id,
                "marketplace_id": self.marketplace_id,
                "asin": asin,
                "match_sources": [*discovered_row["match_sources"], *(["manual"] if asin == manual_asin else [])],
                "compatibility_status": compatibility.status,
                "compatibility_reason_codes": list(compatibility.reason_codes),
                "compatibility_details": compatibility.details,
                "evaluator_version": EVALUATOR_VERSION,
                "prior_account_sale": asin in prior_sales,
                "keepa_sales_rank_drops90": velocity.get("sales_rank_drops90"),
                "keepa_captured_at": velocity.get("captured_at"),
                "last_discovered_at": now_iso(),
                "last_enriched_at": now_iso(),
                "updated_at": now_iso(),
            })

        eligibility = self._eligibility(compatible_asins)
        for row in candidate_rows:
            evidence = eligibility.get(row["asin"])
            if evidence:
                row.update({
                    "eligibility_status": evidence["eligibility_status"],
                    "eligibility_checked_at": evidence["checked_at"],
                    "eligibility_expires_at": evidence["expires_at"],
                    "eligibility_reason_codes": evidence.get("reason_codes") or [],
                })
                row["eligibility_is_fresh"] = True

        ranked = sorted(candidate_rows, key=lambda row: (
            0 if row["compatibility_status"] == "compatible" else 1,
            0 if row.get("eligibility_status") == "eligible" else 1,
            -int(row.get("prior_account_sale") or False),
            -(row.get("keepa_sales_rank_drops90") if row.get("keepa_sales_rank_drops90") is not None else -1),
            row["asin"],
        ))
        for position, row in enumerate(ranked, 1):
            row["rank_position"] = position
            row["ranking_rationale"] = {
                "prior_account_sale": row["prior_account_sale"],
                "keepa_sales_rank_drops90": row.get("keepa_sales_rank_drops90"),
                "unknown_velocity_ranked_last": row.get("keepa_sales_rank_drops90") is None,
            }
            row.pop("eligibility_is_fresh", None)

        persisted = self.repository.replace_candidates(supplier_product_id, self.marketplace_id, ranked)
        selection_inputs = []
        persisted_by_asin = {row["asin"]: row for row in persisted}
        for row in ranked:
            copy = dict(row)
            copy["eligibility_is_fresh"] = bool(copy.get("eligibility_expires_at") and parse_time(copy["eligibility_expires_at"]) > dt.datetime.now(dt.UTC))
            selection_inputs.append(copy)
        selection = select_preferred(selection_inputs, manual_asin)
        if selection.status == "no_candidates" and self._search_errors:
            selection = type(selection)("error", None, "none", {
                "reason": "catalog_search_errors", "errors": self._search_errors,
            })
        selected_id = (persisted_by_asin.get(selection.selected_asin) or {}).get("candidate_id") if selection.selected_asin else None
        signature = identity_signature(product)
        identity_changed = bool(prior_state.get("identity_signature") and prior_state.get("identity_signature") != signature)
        self.repository.upsert_match_state({
            "supplier_product_id": supplier_product_id,
            "marketplace_id": self.marketplace_id,
            "match_status": "identity_review" if identity_changed and selection.status == "matched" else selection.status,
            "selected_candidate_id": None if identity_changed else selected_id,
            "selection_source": "none" if identity_changed else selection.selection_source,
            "identity_signature": signature,
            "identity_changed": identity_changed,
            "rematch_requested": False,
            "selection_rationale": {**selection.rationale, "identity_changed": identity_changed},
            "last_discovered_at": now_iso(), "last_enriched_at": now_iso(), "updated_at": now_iso(),
        })
        return {"supplier_product_id": supplier_product_id, "candidate_count": len(ranked),
                "status": "identity_review" if identity_changed and selection.status == "matched" else selection.status,
                "selected_asin": None if identity_changed else selection.selected_asin}

    def _search(self, product: dict, query_type: str, query_value: str,
                *, force_refresh: bool = False, **kwargs: Any) -> list[dict]:
        product_id = product["supplier_product_id"]
        fingerprint = query_fingerprint(query_type, query_value, self.marketplace_id)
        cached = self.repository.fresh_search(product_id, self.marketplace_id, query_type, fingerprint)
        if cached and not force_refresh:
            if cached.get("search_status") == "error":
                self._search_errors.append(f"{query_type}:{cached.get('error_code') or 'cached_error'}")
            return [{"asin": asin} for asin in cached.get("candidate_asins") or []]
        searched_at = dt.datetime.now(dt.UTC)
        try:
            payload = self.amazon.search_catalog_items(included_data=INCLUDED_DATA, page_size=20, **kwargs)
            items = search_items(payload)
            status = "success" if items else "empty"
            ttl = SEARCH_SUCCESS_TTL if items else SEARCH_EMPTY_TTL
            error_code = error_summary = None
        except AmazonSPAPIError as error:
            items, status, ttl = [], "error", SEARCH_ERROR_TTL
            error_code, error_summary = "amazon_spapi_error", str(error)[:1000]
            self._search_errors.append(f"{query_type}:{error_code}")
        self.repository.save_search({
            "supplier_product_id": product_id, "marketplace_id": self.marketplace_id,
            "query_type": query_type, "query_fingerprint": fingerprint,
            "query_value": query_value, "search_status": status,
            "candidate_asins": [row["asin"] for row in items], "error_code": error_code,
            "error_summary": error_summary, "searched_at": searched_at.isoformat(),
            "expires_at": (searched_at + ttl).isoformat(), "updated_at": searched_at.isoformat(),
        })
        return items

    def _catalog_snapshots(self, asins: list[str]) -> dict[str, dict]:
        snapshots = self.repository.catalog_snapshots(asins)
        cutoff = dt.datetime.now(dt.UTC) - CATALOG_TTL
        for asin in asins:
            row = snapshots.get(asin)
            if row and parse_time(row.get("fetched_at")) > cutoff:
                continue
            payload = self.amazon.get_catalog_item(asin, included_data=INCLUDED_DATA)
            row = normalize_catalog_item(asin, payload, self.marketplace_id)
            self.repository.save_catalog_snapshot(row)
            snapshots[asin] = row
        return snapshots

    def _eligibility(self, asins: list[str]) -> dict[str, dict]:
        rows = self.repository.fresh_eligibility(self.seller_id, self.marketplace_id, asins)
        for asin in asins:
            if asin in rows:
                continue
            checked = dt.datetime.now(dt.UTC)
            try:
                result = classify_restriction_payload(asin, self.amazon.get_listings_restrictions(asin, condition_type="new_new"))
                status = "eligible" if result.status == "sellable" else "restricted" if result.status in {"not_eligible", "approval_required", "asin_not_found"} else "unknown"
                ttl = ELIGIBILITY_TTL if status in {"eligible", "restricted"} else UNKNOWN_ELIGIBILITY_TTL
                reasons, messages, raw = result.reason_codes, result.messages, result.raw
            except AmazonSPAPIError as error:
                status, ttl, reasons, messages, raw = "error", UNKNOWN_ELIGIBILITY_TTL, ["amazon_spapi_error"], [str(error)[:1000]], None
            row = {"seller_id": self.seller_id, "marketplace_id": self.marketplace_id,
                   "asin": asin, "condition_type": "new_new", "eligibility_status": status,
                   "reason_codes": reasons, "reason_messages": messages, "raw_response_json": raw,
                   "checked_at": checked.isoformat(), "expires_at": (checked + ttl).isoformat(),
                   "updated_at": checked.isoformat()}
            self.repository.save_eligibility(row)
            rows[asin] = row
        return rows


def parse_time(value: Any) -> dt.datetime:
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def effective_product_identity(product: dict[str, Any]) -> dict[str, Any]:
    """Use the latest raw identity evidence without letting price affect matching."""
    effective = dict(product)
    observation = product.get("latest_observation")
    if isinstance(observation, dict):
        for field in ("raw_title", "raw_system", "raw_identifier", "normalized_identifier", "identifier_type"):
            if observation.get(field) not in (None, ""):
                effective[field] = observation[field]
    return effective


def process_work_batch(repository: WholesaleRepository, service: WholesaleEnrichmentService,
                       work: list[dict[str, Any]]) -> dict[str, int]:
    """Process an already bounded batch; failures remain retryable and do not abort peers."""
    counters = {"processed": 0, "matched": 0, "review": 0, "errors": 0}
    for item in work:
        try:
            repository.update_work(item["work_item_id"], {
                "work_status": "running",
                "attempt_count": int(item.get("attempt_count") or 0) + 1,
                "updated_at": now_iso(),
            })
            outcome = service.enrich_product(item["supplier_product_id"])
            print(outcome)
            counters["matched"] += int(outcome["status"] == "matched")
            counters["review"] += int(outcome["status"] in {"identity_review", "eligibility_pending"})
            repository.update_work(item["work_item_id"], {
                "work_status": "completed", "current_stage": "complete",
                "completed_at": now_iso(), "updated_at": now_iso(),
            })
        except Exception as error:  # one product must not abort a resumable run
            LOGGER.exception("Wholesale enrichment item failed: %s", error)
            counters["errors"] += 1
            repository.update_work(item["work_item_id"], {
                "work_status": "retry", "error_summary": str(error)[:1000],
                "updated_at": now_iso(),
            })
        counters["processed"] += 1
    return counters


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded wholesale Amazon matching enrichment")
    parser.add_argument("--product-id", action="append", default=[])
    parser.add_argument("--run-id", help="Resume pending work from a persistent enrichment run")
    parser.add_argument("--supplier-id", help="Create a persistent enrichment run for an active supplier catalog")
    parser.add_argument("--limit", type=int, default=25)
    args = parser.parse_args()
    if not args.product_id and not args.run_id and not args.supplier_id:
        parser.error("provide --product-id, --run-id, or --supplier-id")
    repository = WholesaleRepository(get_supabase_client())
    amazon = AmazonSPAPIClient.from_env()
    service = WholesaleEnrichmentService(repository, amazon, seller_id=amazon.config.seller_id or os.getenv("AMAZON_SELLER_ID", ""), marketplace_id=amazon.config.marketplace_id)
    run_id = args.run_id
    if args.supplier_id:
        run = repository.create_enrichment_run(args.supplier_id, amazon.config.marketplace_id, args.limit)
        run_id = run["enrichment_run_id"]
        print({"enrichment_run_id": run_id, "status": "created"})
    work = repository.pending_work(run_id, args.limit) if run_id else []
    for product_id in args.product_id[:args.limit]:
        print(service.enrich_product(product_id))
    if run_id and work:
        repository.update_enrichment_run(run_id, {"run_status": "running", "started_at": now_iso(), "updated_at": now_iso()})
    counters = process_work_batch(repository, service, work)
    if run_id and work:
        current = repository.get_enrichment_run(run_id) or {}
        remaining = repository.pending_work(run_id, 1)
        repository.update_enrichment_run(run_id, {
            "run_status": "running" if remaining else ("completed_with_errors" if counters["errors"] else "completed"),
            "processed_count": int(current.get("processed_count") or 0) + counters["processed"],
            "matched_count": int(current.get("matched_count") or 0) + counters["matched"],
            "review_count": int(current.get("review_count") or 0) + counters["review"],
            "error_count": int(current.get("error_count") or 0) + counters["errors"],
            "completed_at": None if remaining else now_iso(), "updated_at": now_iso(),
        })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
