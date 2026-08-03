# Sourcing Matching Feedback V3

Date: 2026-08-02

This is the operator-facing v3 refinement of sourcing matching feedback. The persisted payload version is `matching_feedback_v2` because it is the second durable storage shape after legacy `incorrectRows`.

See `docs/sourcing_matching_feedback_semantics_and_rendering_2026-08-02.md` for the full implementation notes, mappings, Rock Band Track Pack fixture, reporting behavior, tests, and caveats.

## 2026-08-03 Diagnostics Panel Simplification

The dismiss diagnostics panel is now framed around the operator question:

> Why did MBOP think these two products matched?

Presentation-only changes:

- `Derived Identity` shows only Core Game, Installment / Sequel, Platform, Edition / Version, Region, Package Contents, Completeness, and Digital vs Physical.
- Category/Product Type moved out of identity and into `Evidence Used`.
- Core Game prefers backend-normalized Game Name and shared title identity instead of raw marketplace titles.
- `Evidence Used` shows Amazon Title, eBay Title, eBay Game Name, eBay Item Specifics, Description, Photos, and Category.
- Descriptions are stripped to plain text and truncated for preview.
- Photos render up to three compact eBay thumbnails when normalized image URLs are available.
- Backend context rows, duplicated recommendation text, decision trace, `Result: pass`, bare `pass`, and repeated empty values are hidden.
- Hard blocks and warnings are only shown when non-empty.
- A compact `Matching Summary` shows pass/warning/fail/unknown status for Core Game, Platform, Edition, and Region plus the overall recommendation.

No matching rules, diagnostics generation, scoring, rescoring, persistence, or scheduler code changed in this presentation pass.
