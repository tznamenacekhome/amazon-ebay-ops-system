# Shared Supabase Migration Ownership

Last updated: 2026-07-15

MBOP is the canonical migration authority for the Supabase project shared by
MBOP and College Planner. The MBOP repository owns the complete
`supabase/migrations` history for the project, including migrations that create
or alter College Planner objects.

College Planner may use the shared Supabase project at runtime, but the College
Planner repository must not independently run migration or ledger-changing
commands against the shared project.

## Operating Rules

- Only the MBOP repository may run `supabase migration new`,
  `supabase db push`, `supabase migration repair`, or any command that changes
  the shared remote migration ledger.
- Every migration filename must preserve its remote timestamp and include its
  owning application after the timestamp: `mbop_...`, `college_planner_...`, or
  `shared_...`.
- College Planner database changes must be added to this repository under
  `supabase/migrations` with a `college_planner_` filename.
- Codex must run `supabase migration list` before every `supabase db push`.
- The complete shared migration history must be reconciled before pushing.
- Already-applied migrations must never be edited, removed, rewritten, or
  repurposed.
- Do not apply schema SQL directly to the linked database during normal
  development. If an emergency direct application is unavoidable, verify the
  entire migration against the remote schema and immediately reconcile the MBOP
  migration ledger.

## Current Migration Ledger

Read-only `supabase migration list` on 2026-07-15 showed:

| Version | Local | Remote | Owner | Local file |
|---|---|---|---|---|
| 20260711000000 | yes | yes | MBOP | `20260711000000_mbop_add_sourcing_progressive_batches.sql` |
| 20260711030000 | yes | yes | College Planner | `20260711030000_college_planner_mvp_schema.sql` |
| 20260712000000 | yes | yes | MBOP | `20260712000000_mbop_add_sourcing_coverage_cycles.sql` |
| 20260713010000 | yes | yes | College Planner | `20260713010000_college_planner_add_course_catalog_description_metadata.sql` |
| 20260715000000 | yes | yes | MBOP | `20260715000000_mbop_add_sourcing_blocked_asins.sql` |

The College Planner migration SQL was recovered from
`supabase_migrations.schema_migrations` so MBOP now retains the actual SQL
rather than empty foreign-migration markers.

## Ownership Inventory

Inventory source: read-only linked Supabase metadata queries on 2026-07-15.

### MBOP-Owned Objects

MBOP owns application objects in `public` unless specifically documented
otherwise.

Observed `public` tables:

- `alerts`
- `amazon_account_health_snapshots`
- `amazon_fba_customer_return_rows`
- `amazon_fba_inventory_snapshots`
- `amazon_fba_reimbursement_rows`
- `amazon_fba_removal_order_detail_rows`
- `amazon_fba_removal_shipment_detail_rows`
- `amazon_fee_estimates`
- `amazon_finance_balance_snapshots`
- `amazon_inventory`
- `amazon_inventory_cogs_layers`
- `amazon_inventory_planning_snapshots`
- `amazon_listing_snapshots`
- `amazon_report_runs`
- `amazon_repricing_advisor_snoozes`
- `amazon_return_recovery_cases`
- `amazon_return_recovery_events`
- `amazon_sales_cogs_consumption`
- `amazon_sales_finance_transactions`
- `amazon_sales_financial_events`
- `amazon_sales_fulfillment_cost_overrides`
- `amazon_sales_order_items`
- `amazon_sales_orders`
- `amazon_sales_profitability`
- `amazon_seller_feedback_items`
- `amazon_seller_feedback_snapshots`
- `amazon_skus`
- `asin_metrics`
- `business_value_snapshots`
- `customer_returns`
- `fba_shipment_events`
- `fba_shipment_items`
- `fba_shipment_source_items`
- `fba_shipments`
- `fulfillment_shipments`
- `import_batches`
- `inbound_shipment_items`
- `inbound_shipments`
- `informed_listing_snapshots`
- `informed_report_runs`
- `informed_rule_name_overrides`
- `informed_rule_snapshots`
- `inventory_locations`
- `inventory_movements`
- `inventory_positions`
- `inventory_reconciliation_event_items`
- `inventory_reconciliation_events`
- `inventorylab_active_inventory_backfill`
- `inventorylab_inventory_valuation_snapshots`
- `item_condition_history`
- `item_images`
- `keepa_product_history_points`
- `keepa_product_snapshots`
- `listings`
- `manual_item_matches`
- `matching_intelligence_examples`
- `matching_intelligence_receiving_outcomes`
- `non_ebay_purchase_cogs_sources`
- `order_problem_cases`
- `order_problem_events`
- `profitability_snapshots`
- `purchase_items`
- `purchases`
- `return_reasons`
- `revseller_import_rows`
- `sales`
- `scheduler_domain_freshness`
- `scheduler_job_definitions`
- `scheduler_locks`
- `scheduler_run_jobs`
- `scheduler_runs`
- `sourcing_actions`
- `sourcing_ai_observations`
- `sourcing_blocked_asins`
- `sourcing_coverage_cycle_items`
- `sourcing_coverage_cycles`
- `sourcing_ebay_candidates`
- `sourcing_listing_snapshots`
- `sourcing_opportunities`
- `sourcing_opportunity_batch_items`
- `sourcing_opportunity_batches`
- `sourcing_purchase_matches`
- `sourcing_runs`
- `sourcing_seed_asins`
- `sourcing_seller_intelligence`
- `sourcing_settings`
- `supplier_returns`
- `sync_logs`
- `tracking_events`
- `veeqo_sales_orders`
- `veeqo_sales_shipments`
- `ynab_business_transactions`
- `ynab_category_balance_snapshots`

Observed `public` views:

- `vw_amazon_sales_orders_recent`
- `vw_amazon_sales_summary`
- `vw_current_amazon_inventory_cogs`
- `vw_inventory_position_summary`
- `vw_latest_amazon_fba_inventory_snapshot`
- `vw_latest_amazon_finance_balance_snapshot`
- `vw_latest_amazon_inventory_planning_snapshot`
- `vw_latest_amazon_listing_snapshot`
- `vw_latest_informed_listing_snapshot`
- `vw_latest_informed_rule_snapshot`
- `vw_latest_inventorylab_inventory_valuation`
- `vw_latest_keepa_product_snapshot`
- `vw_latest_ynab_category_balance_snapshot`
- `vw_open_inventory_reconciliation_items`
- `vw_purchases_dashboard`

### College Planner-Owned Objects

College Planner owns objects in the `college_planner` schema.

Observed `college_planner` tables:

- `academic_record_statuses`
- `academic_terms`
- `academic_years`
- `application_users`
- `confidence_levels`
- `core_curriculum_versions`
- `course_aliases`
- `course_offerings`
- `course_relationship_groups`
- `course_relationship_options`
- `course_sections`
- `courses`
- `degree_plans`
- `degree_program_versions`
- `degree_programs`
- `degree_requirement_groups`
- `degree_requirement_options`
- `delivery_methods`
- `import_batches`
- `import_errors`
- `import_files`
- `import_statuses`
- `plan_statuses`
- `planned_courses`
- `planned_terms`
- `requirement_exceptions`
- `requirement_option_courses`
- `requirement_option_tags`
- `section_meetings`
- `source_records`
- `source_types`
- `student_academic_records`
- `student_access_grants`
- `student_profiles`
- `student_programs`
- `subjects`
- `term_parts`
- `universities`
- `university_catalogs`
- `user_roles`

Observed `college_planner` functions:

- `college_planner.set_updated_at`

Observed `college_planner` views:

- None.

### Intentionally Shared Objects

There are currently no intentionally shared application data tables or views.

The following project-level objects are shared infrastructure and must be
treated as project-wide:

- Supabase project and database instance
- `supabase_migrations.schema_migrations`
- Supabase-managed auth, storage, realtime, extension, and system schemas
- database roles and service credentials configured for the shared project

### Ownership Needs Review

The following `public` objects are MBOP-owned by current convention, but their
business ownership or retirement status should be reviewed before future schema
work because their names are generic or legacy:

- `alerts`
- `customer_returns`
- `fulfillment_shipments`
- `import_batches`
- `profitability_snapshots`
- `return_reasons`
- `sales`
- `supplier_returns`

Do not move, rename, or drop these objects without a separate ownership and
usage audit.
