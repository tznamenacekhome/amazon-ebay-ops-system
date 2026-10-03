"""Server-side repository for supplier imports and wholesale matching state."""
from __future__ import annotations

import datetime as dt


class WholesaleRepository:
    def __init__(self, client):
        self.client = client

    def apply_import(self, payload: dict, replaces_import_id: str | None = None) -> dict:
        return self.client.rpc("wholesale_apply_import", {
            "p_payload": payload, "p_replaces_import_id": replaces_import_id,
        }).execute().data

    def list_products(self, supplier_id: str, *, offset: int = 0, limit: int = 100,
                      present_only: bool = False) -> list[dict]:
        self._page(offset, limit)
        query = (self.client.table("vw_wholesale_supplier_products").select("*")
                 .eq("supplier_id", supplier_id))
        if present_only:
            query = query.eq("present_in_latest_list", True)
        return query.order("supplier_product_id").range(offset, offset + limit - 1).execute().data or []

    def get_product(self, supplier_product_id: str) -> dict | None:
        rows = (self.client.table("vw_wholesale_supplier_products").select("*")
                .eq("supplier_product_id", supplier_product_id).limit(1).execute().data or [])
        return rows[0] if rows else None

    def get_matching_detail(self, supplier_product_id: str, marketplace_id: str) -> dict:
        state_rows = (self.client.table("wholesale_match_states").select("*")
                      .eq("supplier_product_id", supplier_product_id)
                      .eq("marketplace_id", marketplace_id).limit(1).execute().data or [])
        candidates = (self.client.table("wholesale_amazon_candidates").select("*")
                      .eq("supplier_product_id", supplier_product_id)
                      .eq("marketplace_id", marketplace_id)
                      .order("rank_position").order("asin").execute().data or [])
        return {"product": self.get_product(supplier_product_id),
                "match_state": state_rows[0] if state_rows else None,
                "candidates": candidates}

    def fresh_search(self, supplier_product_id: str, marketplace_id: str,
                     query_type: str, fingerprint: str) -> dict | None:
        rows = (self.client.table("wholesale_catalog_searches").select("*")
                .eq("supplier_product_id", supplier_product_id)
                .eq("marketplace_id", marketplace_id).eq("query_type", query_type)
                .eq("query_fingerprint", fingerprint)
                .gt("expires_at", self._now()).limit(1).execute().data or [])
        return rows[0] if rows else None

    def save_search(self, row: dict) -> None:
        self.client.table("wholesale_catalog_searches").upsert(
            row, on_conflict="supplier_product_id,marketplace_id,query_type,query_fingerprint"
        ).execute()

    def catalog_snapshots(self, asins: list[str]) -> dict[str, dict]:
        if not asins:
            return {}
        rows = (self.client.table("amazon_catalog_item_identity_snapshots").select("*")
                .in_("asin", asins).execute().data or [])
        return {row["asin"]: row for row in rows}

    def save_catalog_snapshot(self, row: dict) -> None:
        self.client.table("amazon_catalog_item_identity_snapshots").upsert(
            row, on_conflict="asin"
        ).execute()

    def prior_sale_asins(self, asins: list[str]) -> set[str]:
        if not asins:
            return set()
        rows = (self.client.table("amazon_sales_order_items").select("asin")
                .in_("asin", asins).execute().data or [])
        return {row["asin"] for row in rows if row.get("asin")}

    def keepa_velocity(self, asins: list[str]) -> dict[str, dict]:
        if not asins:
            return {}
        rows = (self.client.table("keepa_product_snapshots")
                .select("asin,sales_rank_drops90,captured_at")
                .eq("domain_id", 1).in_("asin", asins)
                .order("captured_at", desc=True).execute().data or [])
        output = {}
        for row in rows:
            output.setdefault(row["asin"], row)
        return output

    def fresh_eligibility(self, seller_id: str, marketplace_id: str, asins: list[str],
                          condition_type: str = "new_new") -> dict[str, dict]:
        if not asins:
            return {}
        rows = (self.client.table("amazon_listing_eligibility_evidence").select("*")
                .eq("seller_id", seller_id).eq("marketplace_id", marketplace_id)
                .eq("condition_type", condition_type).in_("asin", asins)
                .gt("expires_at", self._now()).execute().data or [])
        return {row["asin"]: row for row in rows}

    def save_eligibility(self, row: dict) -> None:
        self.client.table("amazon_listing_eligibility_evidence").upsert(
            row, on_conflict="seller_id,marketplace_id,asin,condition_type"
        ).execute()

    def replace_candidates(self, supplier_product_id: str, marketplace_id: str,
                           rows: list[dict]) -> list[dict]:
        asins = [row["asin"] for row in rows]
        query = (self.client.table("wholesale_amazon_candidates").delete()
                 .eq("supplier_product_id", supplier_product_id)
                 .eq("marketplace_id", marketplace_id))
        if asins:
            query = query.not_.in_("asin", asins)
        query.execute()
        if not rows:
            return []
        return (self.client.table("wholesale_amazon_candidates").upsert(
            rows, on_conflict="supplier_product_id,marketplace_id,asin"
        ).execute().data or [])

    def upsert_match_state(self, row: dict) -> dict:
        return self.client.table("wholesale_match_states").upsert(
            row, on_conflict="supplier_product_id,marketplace_id"
        ).execute().data

    def set_manual_candidate(self, supplier_product_id: str, marketplace_id: str,
                             asin: str | None, actor: str | None = None) -> dict:
        return self.client.rpc("wholesale_set_manual_candidate", {
            "p_supplier_product_id": supplier_product_id,
            "p_marketplace_id": marketplace_id,
            "p_asin": asin,
            "p_actor": actor,
        }).execute().data

    def request_rematch(self, supplier_product_id: str, marketplace_id: str,
                        actor: str | None = None) -> dict:
        return self.client.rpc("wholesale_request_rematch", {
            "p_supplier_product_id": supplier_product_id,
            "p_marketplace_id": marketplace_id,
            "p_actor": actor,
        }).execute().data

    def create_enrichment_run(self, supplier_id: str, marketplace_id: str,
                              limit: int = 100) -> dict:
        self._page(0, limit)
        run = (self.client.table("wholesale_enrichment_runs").insert({
            "supplier_id": supplier_id, "marketplace_id": marketplace_id,
            "requested_limit": limit, "run_status": "pending",
        }).execute().data or [])[0]
        products = (self.client.table("wholesale_supplier_products")
                    .select("supplier_product_id").eq("supplier_id", supplier_id)
                    .eq("is_active", True).order("supplier_product_id")
                    .limit(limit).execute().data or [])
        if products:
            self.client.table("wholesale_enrichment_work_items").insert([{
                "enrichment_run_id": run["enrichment_run_id"],
                "supplier_product_id": row["supplier_product_id"],
            } for row in products]).execute()
        return run

    def pending_work(self, enrichment_run_id: str, limit: int = 25) -> list[dict]:
        self._page(0, limit)
        return (self.client.table("wholesale_enrichment_work_items").select("*")
                .eq("enrichment_run_id", enrichment_run_id)
                .in_("work_status", ["pending", "retry"])
                .order("created_at").limit(limit).execute().data or [])

    def get_enrichment_run(self, enrichment_run_id: str) -> dict | None:
        rows = (self.client.table("wholesale_enrichment_runs").select("*")
                .eq("enrichment_run_id", enrichment_run_id).limit(1).execute().data or [])
        return rows[0] if rows else None

    def update_enrichment_run(self, enrichment_run_id: str, values: dict) -> None:
        self.client.table("wholesale_enrichment_runs").update(values).eq(
            "enrichment_run_id", enrichment_run_id
        ).execute()

    def update_work(self, work_item_id: str, values: dict) -> None:
        self.client.table("wholesale_enrichment_work_items").update(values).eq(
            "work_item_id", work_item_id
        ).execute()

    def ensure_opportunity(self, supplier_product_id: str, marketplace_id: str,
                           candidate_id: str | None, observation_id: str | None) -> dict:
        rows = self.client.table("wholesale_opportunities").upsert({
            "supplier_product_id": supplier_product_id,
            "marketplace_id": marketplace_id,
            "current_candidate_id": candidate_id,
            "current_observation_id": observation_id,
            "evaluation_requested": True,
            "updated_at": self._now(),
        }, on_conflict="supplier_product_id,marketplace_id").execute().data or []
        return rows[0]

    def observation_history(self, supplier_product_id: str) -> list[dict]:
        return (self.client.table("vw_wholesale_observation_history").select("*")
                .eq("supplier_product_id", supplier_product_id).eq("is_superseded", False)
                .order("effective_date").order("revision").execute().data or [])

    def latest_keepa_snapshot(self, asin: str) -> dict | None:
        rows = (self.client.table("keepa_product_snapshots").select("*")
                .eq("asin", asin).eq("domain_id", 1)
                .order("captured_at", desc=True).limit(1).execute().data or [])
        return rows[0] if rows else None

    def fee_estimate(self, asin: str, marketplace_id: str, price: float | None) -> dict | None:
        if price is None:
            return None
        rows = (self.client.table("amazon_fee_estimates").select("*")
                .eq("asin", asin).eq("marketplace_id", marketplace_id)
                .eq("fulfillment_channel", "AFN").eq("listing_price", round(price, 2))
                .eq("shipping_price", 0).eq("currency", "USD").eq("estimate_status", "ok")
                .order("updated_at", desc=True).limit(1).execute().data or [])
        return rows[0] if rows else None

    def inventory_exposure(self, asin: str, marketplace_id: str) -> dict[str, int]:
        rows = (self.client.table("amazon_fba_inventory_snapshots")
                .select("captured_at,fulfillable_quantity,inbound_working_quantity,inbound_shipped_quantity,inbound_receiving_quantity")
                .eq("asin", asin).eq("marketplace_id", marketplace_id)
                .order("captured_at", desc=True).limit(500).execute().data or [])
        if not rows:
            return {"fba_fulfillable_units": 0, "inbound_units": 0}
        newest = rows[0].get("captured_at")
        current = [row for row in rows if row.get("captured_at") == newest]
        integer = lambda value: max(int(value or 0), 0)
        return {
            "fba_fulfillable_units": sum(integer(row.get("fulfillable_quantity")) for row in current),
            "inbound_units": sum(integer(row.get("inbound_working_quantity")) +
                                 integer(row.get("inbound_shipped_quantity")) +
                                 integer(row.get("inbound_receiving_quantity")) for row in current),
        }

    def active_draft_units(self, supplier_product_id: str, marketplace_id: str) -> int:
        rows = (self.client.table("wholesale_order_candidates").select("quantity")
                .eq("supplier_product_id", supplier_product_id).eq("marketplace_id", marketplace_id)
                .eq("commitment_status", "draft").execute().data or [])
        return sum(max(int(row.get("quantity") or 0), 0) for row in rows)

    def save_evaluation(self, opportunity: dict, row: dict) -> dict:
        rows = self.client.table("wholesale_evaluations").upsert(
            row, on_conflict="opportunity_id,input_fingerprint"
        ).execute().data or []
        evaluation = rows[0]
        previous_fingerprint = None
        if opportunity.get("current_evaluation_id"):
            prior = (self.client.table("wholesale_evaluations").select("input_fingerprint")
                     .eq("evaluation_id", opportunity["current_evaluation_id"]).limit(1).execute().data or [])
            previous_fingerprint = prior[0].get("input_fingerprint") if prior else None
        status, active_scope, resurfaced = resolve_opportunity_state(
            row, opportunity.get("active_decision_scope"), previous_fingerprint,
            row["input_fingerprint"], self.active_draft_units(row["supplier_product_id"], row["marketplace_id"]),
        )
        if resurfaced:
            self.client.table("wholesale_decisions").insert({
                "opportunity_id": opportunity["opportunity_id"],
                "evaluation_id": evaluation["evaluation_id"],
                "candidate_id": row.get("candidate_id"),
                "decision_action": "automatic_resurface",
                "decision_scope": "system",
                "reason_code": opportunity.get("active_decision_reason"),
                "actor": "wholesale-evaluator",
                "decision_context": {"previous_fingerprint": previous_fingerprint,
                                     "new_fingerprint": row["input_fingerprint"]},
            }).execute()
        updated = (self.client.table("wholesale_opportunities").update({
            "current_candidate_id": row.get("candidate_id"),
            "current_observation_id": row.get("observation_id"),
            "current_evaluation_id": evaluation["evaluation_id"],
            "opportunity_status": status,
            "active_decision_scope": active_scope,
            "active_decision_reason": opportunity.get("active_decision_reason") if active_scope else None,
            "evaluation_requested": False,
            "updated_at": self._now(),
        }).eq("opportunity_id", opportunity["opportunity_id"]).execute().data or [])
        return {"evaluation": evaluation, "opportunity": updated[0] if updated else None}

    def history(self, supplier_product_id: str, *, offset: int = 0, limit: int = 100,
                include_superseded: bool = False) -> list[dict]:
        self._page(offset, limit)
        query = (self.client.table("vw_wholesale_observation_history").select("*")
                 .eq("supplier_product_id", supplier_product_id))
        if not include_superseded:
            query = query.eq("is_superseded", False)
        return (query.order("effective_date", desc=True).order("revision", desc=True)
                .order("observation_id").range(offset, offset + limit - 1).execute().data or [])

    @staticmethod
    def _page(offset: int, limit: int) -> None:
        if offset < 0 or not 1 <= limit <= 500:
            raise ValueError("offset must be nonnegative and limit must be between 1 and 500")

    @staticmethod
    def _now() -> str:
        return dt.datetime.now(dt.UTC).isoformat()


def opportunity_status(evaluation: dict) -> str:
    status = evaluation.get("evaluation_status")
    if status == "pending_matching":
        return "pending_matching"
    if status in {"pending_eligibility", "restricted"}:
        return "pending_eligibility"
    if status != "complete":
        return "evaluation_incomplete"
    return "ready_for_review" if evaluation.get("is_financially_qualified") else "not_financially_qualified"


def resolve_opportunity_state(evaluation: dict, active_scope: str | None,
                              previous_fingerprint: str | None, new_fingerprint: str,
                              draft_units: int) -> tuple[str, str | None, bool]:
    if active_scope == "hard":
        return "hard_passed", "hard", False
    if draft_units > 0:
        return "added_to_order", active_scope, False
    if active_scope == "temporary" and previous_fingerprint == new_fingerprint:
        return "temporarily_passed", "temporary", False
    if active_scope == "temporary":
        return opportunity_status(evaluation), None, True
    return opportunity_status(evaluation), active_scope, False
