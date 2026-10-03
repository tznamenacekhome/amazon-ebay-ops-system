# Wholesale Purchasing Phase 3B: Deliberate Opportunity Evaluation

Phase 3B turns the Phase 3 queue into a focused review workflow while retaining the dense table for scanning and exception work.

## Review workflow

`/wholesale` now opens an opportunity evaluation workspace from either **Start review queue** or **Evaluate**. The workspace keeps the supplier item and selected Amazon listing side by side, followed by the two independent ROI cases, cost assumptions, inventory and capacity, and informational risk evidence.

The selected listing explains its discovery sources, selection source, compatibility reason codes, ranking rationale, and whether the account previously sold the ASIN. Pending matching, eligibility, and incomplete-economics states use explicit operator-facing explanations.

Add to Order and Pass remain direct actions. A successful add or pass removes the reviewed row from the active queue and opens the next opportunity when one remains. No supplier purchase order is created.

## Candidate comparison and recalculation

Candidate comparison enriches every candidate from existing Amazon Catalog and Keepa caches. It displays title, image, ASIN link, platform, edition, region, format, product type, current Buy Box, 90-day average, discovery sources, ranking evidence, prior sales, velocity, compatibility, and eligibility.

A manual choice still passes through `wholesale_set_manual_candidate`, which accepts only compatible candidates with fresh eligible evidence. In cloud deployment, the API launches exactly one scheduler task:

```text
python integrations/wholesale_evaluate_opportunities.py --product-id <UUID> --marketplace-id ATVPDKIKX0DER --limit 1
```

The dialog polls the existing opportunity detail endpoint until evaluation is no longer requested and the new evaluation references the selected ASIN. The operator stays in the workflow during recalculation. Amazon and Keepa are never called during rendering or selection; evaluation consumes cached evidence.

## Production sequence

Phase 3B adds no schema migration. Production still requires the Phase 1 through Phase 3 migrations, the scheduler image containing the wholesale workers, and the web image containing the API/UI changes. The bounded first run is:

1. import the real supplier workbook with its effective date;
2. run Phase 2 enrichment for a small supplier batch;
3. fetch exact Product Fees evidence for selected ASIN price points;
4. evaluate the same bounded product set;
5. verify queue counts, one detailed opportunity, candidate comparison, pending explanations, and authenticated mutation protection.

Validation is recorded in the deployment report after production rollout.
