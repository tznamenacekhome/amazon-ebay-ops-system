"""Normalize sourcing matching-feedback payloads.

The feedback model separates the matching rule family that failed from the
evidence the operator used to reach that conclusion. Historical `incorrectRows`
payloads remain readable through the same normalization path.
"""

from __future__ import annotations

from typing import Any
from copy import deepcopy
from datetime import datetime


VERSION = "matching_feedback_v3"


def apply_scoped_reviews(comparison, candidate, seed, reviews, *, evaluated_at):
    """Offline Phase 3 application of action-linked v3 evidence.

    Exact identifiers (including variation) are never reduced to a legacy ID.
    Later labels are excluded at the evaluation cutoff. Corrections and verdict
    supersession are independent. Unverifiable/changed snapshots require review.
    This function cannot write, clear a hold, or change a lifecycle status.
    """
    from video_game_identity import evidence_hash, phase3_comparison, IDENTITY_FIELDS, normalize_number_value, normalize_system, platform_display

    def instant(value):
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    def material(snapshot, side):
        if side == "amazon":
            return {"title": snapshot.get("amazon_title"), "system": snapshot.get("amazon_system")}
        raw = snapshot.get("raw_ebay_json") or {}
        return {"title": snapshot.get("ebay_title"), "aspects": raw.get("localizedAspects"),
                "description": raw.get("description") or raw.get("shortDescription"),
                "image": raw.get("image"), "additionalImages": raw.get("additionalImages"),
                "condition": snapshot.get("ebay_condition")}

    current = {"amazon_title": seed.get("amazon_title"), "amazon_system": seed.get("system"),
               "ebay_title": candidate.get("ebay_title"), "raw_ebay_json": candidate.get("raw_ebay_json"),
               "ebay_condition": candidate.get("condition")}
    identity = deepcopy(comparison)
    audit, eligible = [], []
    cutoff = instant(evaluated_at)
    for row in reviews:
        feedback = (row.get("raw_action_context") or {}).get("matchingFeedback") or {}
        if row.get("asin") != seed.get("asin") or feedback.get("version") != VERSION or feedback.get("evidenceProvenance") != "explicit":
            continue
        if not row.get("action_id") or not row.get("created_at"):
            continue
        try:
            when = instant(row["created_at"])
            if when > cutoff: continue
        except (ValueError, TypeError):
            continue
        eligible.append((when, str(row["action_id"]), row, feedback))
    eligible.sort(key=lambda row: row[:2], reverse=True)
    correction_keys = set()
    verdict_row = None
    for _, action_id, row, feedback in eligible:
        exact = row.get("ebay_item_id") == candidate.get("ebay_item_id")
        snapshot = row.get("snapshot") or {}
        snapshot_ok = snapshot.get("action_id") == action_id and snapshot.get("asin") == seed.get("asin") and snapshot.get("ebay_item_id") == row.get("ebay_item_id")
        unchanged = {side: snapshot_ok and evidence_hash(material(snapshot, side)) == evidence_hash(material(current, side)) for side in ("amazon", "ebay")}
        # Catalog metadata was not stored in v3 listing snapshots. Until its
        # reviewed source can be reconciled, never assume it was unchanged.
        if (seed.get("raw_context_json") or {}).get("amazon_catalog_identity"):
            unchanged["amazon"] = False
        if exact and verdict_row is None and feedback.get("pairVerdict") in {"correct", "incorrect", "unsure"}:
            verdict_row = (action_id, feedback["pairVerdict"], all(unchanged.values()))
        for correction in feedback.get("corrections") or []:
            key, side, scope = correction.get("field"), correction.get("side"), correction.get("scope")
            if key not in IDENTITY_FIELDS or side not in {"amazon", "ebay"}: continue
            if scope != "pair" and not (scope == "asin" and side == "amazon"): continue
            if scope == "pair" and not exact: continue
            correction_key = (key, side)
            if correction_key in correction_keys: continue
            correction_keys.add(correction_key)
            entry = {"actionId": action_id, "field": key, "side": side, "scope": scope,
                     "operatorBefore": correction.get("before"), "snapshotId": snapshot.get("listing_snapshot_id")}
            state = correction.get("state")
            valid = state in {"supported", "inferred", "unknown", "explicit_absence"} and (state in {"unknown", "explicit_absence"} or bool(correction.get("value")))
            if not valid or not unchanged[side]:
                audit.append({**entry, "result": "needs_review", "reason": "Invalid correction or changed/unverifiable source snapshot"})
                continue
            old = deepcopy(identity[side]["fields"][key])
            value = None if state == "unknown" else correction.get("value")
            if state == "explicit_absence": value = "Explicitly absent"
            elif value and key == "platform": value = platform_display(normalize_system(value)) or value
            elif value and key == "installment": value = normalize_number_value(value)
            identity[side]["fields"][key].update(value=value, state=state, sources=[{"field": "operator_correction", "actionId": action_id,
                "snapshot": snapshot.get("listing_snapshot_id"), "scope": scope}], before=old)
            identity[side][key] = value
            if key == "installment": identity[side]["installmentNormalized"] = value
            audit.append({**entry, "result": "applied"})
    result = phase3_comparison(identity["amazon"], identity["ebay"])
    result.update({key: comparison[key] for key in ("reference", "materialEvidenceHash") if key in comparison})
    if verdict_row:
        action_id, verdict, unchanged = verdict_row
        applied_verdict = {"correct": "match", "incorrect": "non-match", "unsure": "needs_review"}[verdict] if unchanged else "needs_review"
        result["evidenceDecision"]["productIdentityVerdict"] = applied_verdict
        verdict_time = next(row[2]['created_at'] for row in eligible if row[1] == action_id)
        result["evidenceDecision"]["operatorVerdict"] = {"actionId": action_id, "createdAt": verdict_time, "verdict": verdict, "result": "applied" if unchanged else "needs_review", "reason": "Exact reviewed sources unchanged" if unchanged else "New or unverifiable material evidence"}
        result["result"] = {"match": "match", "non-match": "conflict", "needs_review": "review"}[applied_verdict]
        result["hard_block"] = applied_verdict == "non-match"
        result["reason"] = "Exact-pair operator verdict: " + applied_verdict
    if any(row["result"] == "needs_review" for row in audit):
        result["evidenceDecision"]["productIdentityVerdict"] = "needs_review"
        result["result"], result["hard_block"] = "review", False
        result["reason"] = "Field correction requires re-review of changed or unverifiable evidence"
    result["correctionApplication"] = audit
    return result

RULE_FAMILIES = {
    "core_game_identity",
    "numeric_installment",
    "platform",
    "edition_version",
    "region",
    "completeness",
    "digital_physical",
    "category_product_type",
    "seller_listing_photo_consistency",
    "other",
}

EVIDENCE_SOURCES = {
    "amazon_title",
    "ebay_title",
    "ebay_game_name",
    "ebay_item_specifics",
    "amazon_catalog_metadata",
    "ebay_description",
    "primary_image",
    "additional_images",
    "category",
    "platform_metadata",
    "other",
}

LEGACY_ROW_RULE_FAMILY = {
    "core_game_identity": "core_game_identity",
    "platform_system": "platform",
    "installment_number": "numeric_installment",
    "numeric_installment": "numeric_installment",
    "edition_version": "edition_version",
    "region": "region",
    "package_bundle_contents": "completeness",
    "completeness": "completeness",
    "digital_physical": "digital_physical",
    "category": "category_product_type",
    "format_type": "category_product_type",
    "seller_listing_photo_consistency": "seller_listing_photo_consistency",
}

LEGACY_ROW_EVIDENCE_SOURCE = {
    "full_title": ["amazon_title", "ebay_title"],
    "game_name": ["ebay_game_name"],
    "platform_system": ["platform_metadata"],
    "category": ["category"],
    "format_type": ["ebay_item_specifics"],
    "release_year": ["ebay_item_specifics"],
    "package_bundle_contents": ["ebay_item_specifics"],
    "seller_listing_photo_consistency": ["primary_image", "additional_images"],
    "item_location": ["other"],
}

RULE_FAMILY_EVIDENCE_DEFAULTS = {
    "core_game_identity": ["amazon_title", "ebay_title", "ebay_game_name"],
    "numeric_installment": ["amazon_title", "ebay_title", "ebay_item_specifics"],
    "platform": ["amazon_title", "ebay_title", "platform_metadata", "ebay_item_specifics"],
    "edition_version": ["amazon_title", "ebay_title", "ebay_item_specifics"],
    "region": ["ebay_item_specifics", "category"],
    "completeness": ["ebay_title", "ebay_item_specifics", "ebay_description", "primary_image", "additional_images"],
    "digital_physical": ["ebay_title", "ebay_item_specifics", "ebay_description", "category"],
    "category_product_type": ["category", "ebay_item_specifics", "ebay_title"],
    "seller_listing_photo_consistency": ["primary_image", "additional_images", "ebay_title"],
    "other": ["other"],
}


def normalize_matching_feedback(value: Any) -> dict[str, Any]:
    record = value if isinstance(value, dict) else {}
    nested = record.get("matchingFeedback")
    if isinstance(nested, dict):
        record = nested

    current = record.get("version") == VERSION
    all_correct = record.get("allAssumptionsCorrect") is True
    legacy_rows = string_list(record.get("legacyIncorrectRows"))
    legacy_rows.extend(item for item in string_list(record.get("incorrectRows")) if item not in legacy_rows)

    failed = normalize_values(record.get("failedRuleFamilies"), RULE_FAMILIES)
    if not failed:
        failed = legacy_rule_families(legacy_rows)

    evidence = normalize_values(record.get("evidenceSources"), EVIDENCE_SOURCES)
    if not current:
        evidence.extend(item for item in legacy_evidence_sources(legacy_rows) if item not in evidence)
        evidence.extend(item for item in evidence_for_rule_families(failed) if item not in evidence)

    if all_correct:
        failed = []
        if not current:
            evidence = []

    return {
        "version": VERSION if current else "matching_feedback_v2",
        "allAssumptionsCorrect": all_correct,
        "failedRuleFamilies": failed,
        "evidenceSources": evidence,
        "legacyIncorrectRows": [] if all_correct else legacy_rows,
        "note": clean_note(record.get("note")),
        "pairVerdict": record.get("pairVerdict") if current and record.get("pairVerdict") in {"correct","incorrect","unsure"} else "not_provided",
        "corrections": [dict(c) for c in record.get("corrections",[]) if isinstance(c,dict)] if current and isinstance(record.get("corrections"),list) else [],
        "availableEvidenceSources": normalize_values(record.get("availableEvidenceSources"),EVIDENCE_SOURCES),
        "evidenceProvenance": "explicit" if current else "legacy_mixed",
    }


def matching_feedback_from_context(context: Any) -> dict[str, Any]:
    if not isinstance(context, dict):
        return normalize_matching_feedback(None)
    if isinstance(context.get("matchingFeedback"), dict):
        return normalize_matching_feedback(context["matchingFeedback"])
    if isinstance(context.get("diagnosticsFeedback"), dict):
        return normalize_matching_feedback(context["diagnosticsFeedback"])
    return normalize_matching_feedback(context)


def evidence_for_rule_families(families: list[str]) -> list[str]:
    output: list[str] = []
    for family in families:
        for source in RULE_FAMILY_EVIDENCE_DEFAULTS.get(family, ["other"]):
            if source not in output:
                output.append(source)
    return output


def legacy_rule_families(rows: list[str]) -> list[str]:
    output: list[str] = []
    for row in rows:
        family = LEGACY_ROW_RULE_FAMILY.get(row)
        if not family and row and row not in LEGACY_ROW_EVIDENCE_SOURCE:
            family = "other"
        if family and family not in output:
            output.append(family)
    return output


def legacy_evidence_sources(rows: list[str]) -> list[str]:
    output: list[str] = []
    for row in rows:
        for source in LEGACY_ROW_EVIDENCE_SOURCE.get(row, []):
            if source not in output:
                output.append(source)
    return output


def normalize_values(value: Any, allowed: set[str]) -> list[str]:
    output: list[str] = []
    for item in string_list(value):
        normalized = normalize_key(item)
        if normalized not in allowed:
            normalized = "other"
        if normalized not in output:
            output.append(normalized)
    return output


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [normalize_key(item) for item in value if normalize_key(item)]


def normalize_key(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def clean_note(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
