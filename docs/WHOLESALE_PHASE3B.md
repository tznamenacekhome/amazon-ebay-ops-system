# Wholesale Purchasing Phase 3B: Deliberate Opportunity Evaluation

Status: deployed and authenticated-browser verified in production on October 3, 2026.

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

Phase 3B adds no schema migration. Production requires the Phase 1 through Phase 3 migrations, the scheduler image containing the wholesale workers, and the web image containing the API/UI changes. The bounded first run is:

1. import the real supplier workbook with its effective date;
2. run Phase 2 enrichment for a small supplier batch;
3. fetch exact Product Fees evidence for selected ASIN price points;
4. evaluate the same bounded product set;
5. verify queue counts, one detailed opportunity, candidate comparison, pending explanations, and authenticated mutation protection.

## Production deployment record

- Supabase project: `froeucjkcepuhgwisped`; all three local/remote migration versions match.
- Royal import: `31d4a7dc-5c5f-4141-881a-bef3cea365a6`; 1,050 products and observations, 17 warnings, zero invalid/conflicting rows.
- Scheduler: task definition revision 109, image digest `sha256:95c909f36e6d3cd8916915d6e56fc1a0ecad8bea674c901ec08eb4a0d6cbbdad`; all 20 schedules updated.
- Web: task definition revision 169, build `695a4335c71e`, image digest `sha256:4f9f804a3df2e465c64bfe795a18dfa51764357f4b72be27bf839d258bab182e`; ECS rollout completed with one healthy task.
- Bounded enrichment run `9ac65747-8e51-4759-90db-01d48b60c5e8`: 10 products total; six matches in the resumed batch, one identity review, two restricted, one completed before the interrupted batch was resumed, and zero final errors.
- Product Fees: two planned calls for selected ASIN `B09D6QWQHD`, two successful cached estimates, zero failures.
- Evaluation: ten immutable evaluations/opportunities. Queue result is 10 pending/incomplete, 0 ready; missing Keepa prices, identity review, restriction, accessory policy, and incomplete dual-price evidence remain explicit.
- Authenticated browser: Purchases, Receiving, Send to Amazon, wholesale queue, focused evaluation, and enriched candidate comparison rendered correctly; browser console reported zero errors.
- No manual candidate mutation, pass, draft commitment, or supplier purchase order was created during verification.
