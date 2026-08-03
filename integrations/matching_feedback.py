"""Normalize sourcing matching-feedback payloads.

The feedback model separates the matching rule family that failed from the
evidence the operator used to reach that conclusion. Historical `incorrectRows`
payloads remain readable through the same normalization path.
"""

from __future__ import annotations

from typing import Any


VERSION = "matching_feedback_v2"

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

    all_correct = bool(record.get("allAssumptionsCorrect"))
    legacy_rows = string_list(record.get("legacyIncorrectRows"))
    legacy_rows.extend(item for item in string_list(record.get("incorrectRows")) if item not in legacy_rows)

    failed = normalize_values(record.get("failedRuleFamilies"), RULE_FAMILIES)
    if not failed:
        failed = legacy_rule_families(legacy_rows)

    evidence = normalize_values(record.get("evidenceSources"), EVIDENCE_SOURCES)
    evidence.extend(item for item in legacy_evidence_sources(legacy_rows) if item not in evidence)
    evidence.extend(item for item in evidence_for_rule_families(failed) if item not in evidence)

    if all_correct:
        failed = []
        evidence = []

    return {
        "version": VERSION,
        "allAssumptionsCorrect": all_correct,
        "failedRuleFamilies": failed,
        "evidenceSources": evidence,
        "legacyIncorrectRows": [] if all_correct else legacy_rows,
        "note": clean_note(record.get("note")),
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
