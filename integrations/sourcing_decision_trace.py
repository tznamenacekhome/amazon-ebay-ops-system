from __future__ import annotations

import datetime as dt
from copy import deepcopy
from typing import Any


RULE_VERSION = "sourcing_decision_trace_v1"
PRESENTABLE_TYPES = {"buy_now", "multi_unit", "best_offer", "auction"}
PRESENTABLE_RECOMMENDATIONS = {"Strong Match", "Probable Match"}

REASON_PRIORITY = [
    ("historical_exact_negative", "Historical Exact Negative", "matching_intelligence", "duplicate_history"),
    ("game_name_conflict", "Different Game Name", "matching_diagnostics", "hard_block"),
    ("numeric_installment_mismatch", "Numeric Installment Mismatch", "matching_diagnostics", "hard_block"),
    ("wrong_platform", "Wrong Platform", "matching_diagnostics", "hard_block"),
    ("edition_version_conflict", "Edition/version conflict", "matching_diagnostics", "hard_block"),
    ("digital_or_service_listing", "Digital or service listing", "matching_diagnostics", "hard_block"),
    ("accessory_not_game", "Accessory / not a game", "matching_diagnostics", "hard_block"),
    ("incomplete_product", "Incomplete product", "matching_diagnostics", "hard_block"),
    ("region_or_location", "Region or location conflict", "matching_diagnostics", "item_location"),
    ("unsupported_platform", "Unsupported Platform", "matching_diagnostics", "unsupported_platform"),
    ("unavailable_listing", "Unavailable listing", "availability", "availability"),
    ("seller_policy", "Seller avoid/watch policy", "seller_intelligence", "seller_rule"),
    ("profitability", "Rejected by profitability", "profitability", "profitability"),
    ("duplicate_history", "Historical operator status", "operator_history", "duplicate_history"),
    ("review_threshold", "Review threshold", "presentation_gate", "review_threshold"),
    ("current_rules_would_present", "Now appears presentation-eligible", "reprocess_current_rules", "other_eligibility_gate"),
    ("unknown_rejection", "Rejected before presentation", "opportunity_status", "other_eligibility_gate"),
]

REASON_META = {
    code: {"code": code, "label": label, "source": source, "severity": severity}
    for code, label, source, severity in REASON_PRIORITY
}

REASON_SUMMARIES = {
    "historical_exact_negative": "Stored matching intelligence blocks this listing from prior negative feedback.",
    "game_name_conflict": "eBay evidence identifies a different game name from the Amazon product.",
    "numeric_installment_mismatch": "Numeric installment, sequel, or identity evidence conflicts.",
    "wrong_platform": "Amazon and eBay platform/system evidence does not match.",
    "edition_version_conflict": "Edition, version, bundle, or package wording conflicts.",
    "digital_or_service_listing": "The listing appears to be digital delivery, DLC, an account, or a service.",
    "accessory_not_game": "Category or title evidence indicates an accessory, merchandise, or non-game item.",
    "incomplete_product": "The listing appears incomplete, disc-only, case-only, or missing expected contents.",
    "region_or_location": "Region, item-location, or pickup-only evidence conflicts with sourcing rules.",
    "unsupported_platform": "The platform is not supported for sourcing presentation.",
    "unavailable_listing": "Stored listing evidence says the item is ended, sold out, or unavailable.",
    "seller_policy": "Seller intelligence reduced or blocked presentation.",
    "profitability": "Profit or ROI did not meet the configured sourcing threshold.",
    "duplicate_history": "Historical operator action kept this listing out of presentation.",
    "review_threshold": "Final matching recommendation required review and did not enter presentation.",
    "current_rules_would_present": "Current diagnostics do not show a blocking rule; keep excluded until operator review.",
    "unknown_rejection": "Status is rejected, but stored diagnostics do not include a mapped rule.",
}

DIAGNOSTIC_KEYS = {
    "historical_exact_negative": ["confidence_summary", "hard_blocks", "warnings"],
    "game_name_conflict": ["game_name", "core_game_identity", "hard_blocks"],
    "numeric_installment_mismatch": ["installment_number", "hard_blocks"],
    "wrong_platform": ["platform_system", "hard_blocks"],
    "edition_version_conflict": ["edition_version", "package_bundle_contents", "hard_blocks"],
    "digital_or_service_listing": ["digital_physical", "hard_blocks"],
    "accessory_not_game": ["category", "format_type", "hard_blocks"],
    "incomplete_product": ["completeness", "package_bundle_contents", "hard_blocks"],
    "region_or_location": ["region", "item_location", "hard_blocks"],
    "unsupported_platform": ["platform_system", "hard_blocks"],
    "unavailable_listing": ["opportunity_context", "hard_blocks"],
    "seller_policy": ["warnings", "confidence_summary"],
    "profitability": ["opportunity_context", "confidence_summary"],
    "duplicate_history": ["opportunity_context", "confidence_summary"],
    "review_threshold": ["final_recommendation", "confidence_summary"],
    "current_rules_would_present": ["final_recommendation", "confidence_summary", "opportunity_context"],
    "unknown_rejection": ["final_recommendation", "confidence_summary", "opportunity_context"],
}


def enrich_sourcing_diagnostics(
    diagnostics: dict[str, Any] | None,
    *,
    status: str | None,
    opportunity_type: str | None,
    profit: float | None,
    roi_percent: float | None,
    listing_status: str | None = None,
    evaluated_at: str | None = None,
) -> dict[str, Any]:
    enriched = deepcopy(diagnostics or {})
    trace = build_decision_trace(
        enriched,
        status=status,
        opportunity_type=opportunity_type,
        profit=profit,
        roi_percent=roi_percent,
        listing_status=listing_status,
    )
    reasons = reasons_from_trace(trace, status=status, opportunity_type=opportunity_type)
    eligible = is_currently_presentable(
        status=status,
        opportunity_type=opportunity_type,
        diagnostics=enriched,
        profit=profit,
        roi_percent=roi_percent,
    )
    primary = None if eligible else reasons[0] if reasons else None
    if eligible:
        reasons = []
    elif primary is None and status == "rejected":
        primary = reason("unknown_rejection")
        reasons = [primary]
    enriched["presentationDecision"] = {
        "eligible": eligible,
        "finalStatus": status,
        "finalOpportunityType": opportunity_type,
        "finalRecommendation": recommendation(enriched),
        "primaryReason": primary,
        "secondaryReasons": reasons[1:],
        "evaluatedAt": evaluated_at or dt.datetime.now(dt.UTC).isoformat(),
        "ruleVersion": RULE_VERSION,
    }
    enriched["decisionTrace"] = trace
    return enriched


def build_decision_trace(
    diagnostics: dict[str, Any],
    *,
    status: str | None,
    opportunity_type: str | None,
    profit: float | None,
    roi_percent: float | None,
    listing_status: str | None,
) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    static_rules = record(diagnostics.get("static_rules"))
    checks = [
        ("title_overlap", "Title overlap", "title_overlap"),
        ("platform_rule", "Platform/system", "platform_system"),
        ("game_name", "Game name", "game_name"),
        ("numeric_identity", "Numeric identity", "installment_number"),
        ("edition_version", "Edition/version", "edition_version"),
        ("category", "Category", "category"),
        ("digital_download", "Digital/physical", "digital_physical"),
        ("incomplete_listing", "Completeness", "completeness"),
        ("not_game", "Accessory/not game", "format_type"),
        ("region", "Region", "region"),
        ("delivery", "Delivery", "item_location"),
        ("location", "Item location", "item_location"),
    ]
    for key, label, diagnostic_key in checks:
        value = record(diagnostics.get(key)) or record(static_rules.get(key))
        if not value:
            continue
        result = result_name(value)
        trace.append(trace_row(label, diagnostic_key, result, summary_for_check(key, value), reason_code_for_check(key, value)))

    if diagnostics.get("historical_negative_count"):
        trace.append(trace_row("Historical feedback", "confidence_summary", "fail", "Historical negative example matched.", "historical_exact_negative"))
    elif diagnostics.get("historical_positive_count"):
        trace.append(trace_row("Historical feedback", "confidence_summary", "pass", "Historical positive match supports the candidate."))
    elif diagnostics.get("historical_business_count") or diagnostics.get("historical_availability_count"):
        trace.append(trace_row("Historical feedback", "confidence_summary", "warning", "Historical operator feedback requires caution.", "duplicate_history"))

    seller_status = str(diagnostics.get("seller_status") or "")
    if seller_status == "avoid":
        trace.append(trace_row("Seller policy", "warnings", "fail", f"Seller is marked avoid: {diagnostics.get('seller_reason') or 'seller intelligence'}.", "seller_policy"))
    elif seller_status == "watch":
        trace.append(trace_row("Seller policy", "warnings", "warning", f"Seller is marked watch: {diagnostics.get('seller_reason') or 'seller intelligence'}.", "seller_policy"))

    if listing_status and str(listing_status).lower() not in {"active", "live"}:
        trace.append(trace_row("Listing availability", "opportunity_context", "fail", f"Listing status is {listing_status}.", "unavailable_listing"))

    final_recommendation = recommendation(diagnostics)
    if profit is None or roi_percent is None:
        trace.append(trace_row("Profitability", "opportunity_context", "fail", "Profit or ROI could not be calculated.", "profitability"))
    elif status == "rejected" and (
        opportunity_type == "no_profitable_source_found"
        or (opportunity_type in PRESENTABLE_TYPES and final_recommendation in PRESENTABLE_RECOMMENDATIONS)
    ):
        trace.append(trace_row("Profitability", "opportunity_context", "fail", f"Estimated profit ${profit} and ROI {roi_percent}% did not qualify at the current ask/terms.", "profitability"))
    else:
        trace.append(trace_row("Profitability", "opportunity_context", "pass", f"Estimated profit ${profit} and ROI {roi_percent}%."))

    if final_recommendation in PRESENTABLE_RECOMMENDATIONS:
        trace.append(trace_row("Final recommendation", "final_recommendation", "pass", f"Final recommendation is {final_recommendation}."))
    elif final_recommendation == "Blocked":
        trace.append(trace_row("Final recommendation", "final_recommendation", "fail", "Final recommendation is Blocked.", "review_threshold"))
    else:
        trace.append(trace_row("Final recommendation", "final_recommendation", "warning", f"Final recommendation is {final_recommendation or 'not available'}.", "review_threshold"))

    if opportunity_type not in PRESENTABLE_TYPES:
        trace.append(trace_row("Presentation gate", "opportunity_context", "fail", f"Opportunity type is {opportunity_type or 'not available'}.", "profitability"))
    elif status != "open":
        trace.append(trace_row("Presentation gate", "opportunity_context", "fail", f"Opportunity status is {status or 'not available'}."))
    else:
        trace.append(trace_row("Presentation gate", "opportunity_context", "pass", "Opportunity is open and presentable."))
    return trace


def reasons_from_trace(trace: list[dict[str, Any]], *, status: str | None, opportunity_type: str | None) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for row in trace:
        if row.get("result") not in {"fail", "warning"}:
            continue
        code = row.get("reasonCode")
        if not code:
            continue
        found.setdefault(str(code), reason(str(code)))
    if status == "rejected" and opportunity_type == "no_profitable_source_found":
        found.setdefault("profitability", reason("profitability"))
    priority = {code: index for index, (code, *_rest) in enumerate(REASON_PRIORITY)}
    return sorted(found.values(), key=lambda item: priority.get(str(item.get("code")), 999))


def is_currently_presentable(
    *,
    status: str | None,
    opportunity_type: str | None,
    diagnostics: dict[str, Any],
    profit: float | None,
    roi_percent: float | None,
) -> bool:
    if status not in {None, "open"}:
        return False
    if opportunity_type not in PRESENTABLE_TYPES:
        return False
    if has_hard_block(diagnostics):
        return False
    if recommendation(diagnostics) not in PRESENTABLE_RECOMMENDATIONS:
        return False
    return profit is not None and roi_percent is not None


def reason(code: str) -> dict[str, Any]:
    meta = REASON_META.get(code, REASON_META["unknown_rejection"])
    return {
        **meta,
        "summary": REASON_SUMMARIES.get(code, REASON_SUMMARIES["unknown_rejection"]),
        "category": meta["severity"],
        "diagnosticKeys": DIAGNOSTIC_KEYS.get(code, DIAGNOSTIC_KEYS["unknown_rejection"]),
    }


def result_name(value: dict[str, Any]) -> str:
    raw = str(value.get("result") or "").lower()
    if raw in {"blocked", "fail"}:
        return "fail"
    if raw in {"review", "warning"}:
        return "warning"
    if raw in {"pass", "matched", "match"}:
        return "pass"
    return "unknown"


def summary_for_check(key: str, value: dict[str, Any]) -> str:
    reason_text = str(value.get("reason") or "").strip()
    if reason_text:
        return reason_text
    hits = value.get("hits")
    if isinstance(hits, list) and hits:
        return f"{key.replace('_', ' ')} hit: {', '.join(str(item) for item in hits[:3])}"
    shared = value.get("shared_tokens") or value.get("shared_title_tokens")
    if isinstance(shared, list) and shared:
        return f"Shared tokens: {', '.join(str(item) for item in shared[:8])}"
    return f"{key.replace('_', ' ')} evaluated."


def reason_code_for_check(key: str, value: dict[str, Any]) -> str | None:
    if result_name(value) == "pass":
        return None
    text = " ".join([key, str(value.get("reason") or ""), " ".join(str(item) for item in value.get("hits") or [])]).lower()
    if "unsupported platform" in text:
        return "unsupported_platform"
    if "platform" in text:
        return "wrong_platform"
    if "game_name" in key or "game name" in text:
        return "game_name_conflict"
    if "numeric" in text or "installment" in text or "identity number" in text:
        return "numeric_installment_mismatch"
    if "edition" in text or "version" in text:
        return "edition_version_conflict"
    if "digital" in text or "download" in text or "dlc" in text or "account" in text:
        return "digital_or_service_listing"
    if "incomplete" in text or "disc only" in text or "case only" in text:
        return "incomplete_product"
    if "category" in text or "not game" in text or "not-game" in text or "accessory" in text:
        return "accessory_not_game"
    if "region" in text or "north-american" in text or "location" in text or "pickup" in text:
        return "region_or_location"
    return None


def trace_row(stage: str, diagnostic_key: str, result: str, summary: str, reason_code: str | None = None) -> dict[str, Any]:
    row = {"stage": stage, "diagnosticKey": diagnostic_key, "result": result, "summary": summary}
    if reason_code:
        row["reasonCode"] = reason_code
    return row


def recommendation(diagnostics: dict[str, Any]) -> str | None:
    static_rules = record(diagnostics.get("static_rules"))
    value = diagnostics.get("recommendation") or static_rules.get("recommendation")
    return str(value) if value else None


def has_hard_block(diagnostics: dict[str, Any]) -> bool:
    static_rules = record(diagnostics.get("static_rules"))
    if recommendation(diagnostics) == "Blocked":
        return True
    return bool(diagnostics.get("hard_blocks") or static_rules.get("hard_blocks") or blocked_flags(diagnostics.get("flags")) or blocked_flags(static_rules.get("flags")))


def blocked_flags(value: Any) -> bool:
    return isinstance(value, list) and any(str(item).startswith("Blocked:") for item in value)


def record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
