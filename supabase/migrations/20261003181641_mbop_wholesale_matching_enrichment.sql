-- Phase 2 wholesale Amazon matching and enrichment.
-- This migration is intentionally local-only until the operator applies it.

create table if not exists public.wholesale_catalog_searches (
    search_id uuid primary key default gen_random_uuid(),
    supplier_product_id uuid not null references public.wholesale_supplier_products(supplier_product_id) on delete cascade,
    marketplace_id text not null,
    query_type text not null check (query_type in ('identifier', 'title_platform')),
    query_fingerprint text not null,
    query_value text not null,
    search_status text not null check (search_status in ('success', 'empty', 'error')),
    candidate_asins jsonb not null default '[]'::jsonb check (jsonb_typeof(candidate_asins) = 'array'),
    error_code text,
    error_summary text,
    searched_at timestamptz not null default now(),
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (supplier_product_id, marketplace_id, query_type, query_fingerprint)
);

create index if not exists wholesale_catalog_searches_lookup_idx
    on public.wholesale_catalog_searches (supplier_product_id, marketplace_id, query_type, expires_at desc);

create table if not exists public.amazon_listing_eligibility_evidence (
    evidence_id uuid primary key default gen_random_uuid(),
    seller_id text not null,
    marketplace_id text not null,
    asin text not null check (asin ~ '^[A-Z0-9]{10}$'),
    condition_type text not null default 'new_new',
    eligibility_status text not null check (eligibility_status in ('eligible', 'restricted', 'unknown', 'error')),
    reason_codes jsonb not null default '[]'::jsonb check (jsonb_typeof(reason_codes) = 'array'),
    reason_messages jsonb not null default '[]'::jsonb check (jsonb_typeof(reason_messages) = 'array'),
    raw_response_json jsonb,
    checked_at timestamptz not null default now(),
    expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (seller_id, marketplace_id, asin, condition_type)
);

create index if not exists amazon_listing_eligibility_evidence_lookup_idx
    on public.amazon_listing_eligibility_evidence (seller_id, marketplace_id, asin, condition_type, expires_at desc);

create table if not exists public.wholesale_amazon_candidates (
    candidate_id uuid primary key default gen_random_uuid(),
    supplier_product_id uuid not null references public.wholesale_supplier_products(supplier_product_id) on delete cascade,
    marketplace_id text not null,
    asin text not null check (asin ~ '^[A-Z0-9]{10}$'),
    match_sources text[] not null default '{}'::text[],
    compatibility_status text not null default 'uncertain' check (compatibility_status in ('compatible', 'incompatible', 'uncertain')),
    compatibility_reason_codes jsonb not null default '[]'::jsonb check (jsonb_typeof(compatibility_reason_codes) = 'array'),
    compatibility_details jsonb not null default '{}'::jsonb check (jsonb_typeof(compatibility_details) = 'object'),
    evaluator_version text not null default 'wholesale-v1',
    prior_account_sale boolean not null default false,
    keepa_sales_rank_drops90 integer,
    keepa_captured_at timestamptz,
    eligibility_status text check (eligibility_status is null or eligibility_status in ('eligible', 'restricted', 'unknown', 'error')),
    eligibility_checked_at timestamptz,
    eligibility_expires_at timestamptz,
    eligibility_reason_codes jsonb not null default '[]'::jsonb check (jsonb_typeof(eligibility_reason_codes) = 'array'),
    rank_position integer,
    ranking_rationale jsonb not null default '{}'::jsonb check (jsonb_typeof(ranking_rationale) = 'object'),
    first_discovered_at timestamptz not null default now(),
    last_discovered_at timestamptz not null default now(),
    last_enriched_at timestamptz,
    updated_at timestamptz not null default now(),
    unique (supplier_product_id, marketplace_id, asin)
);

create index if not exists wholesale_amazon_candidates_product_idx
    on public.wholesale_amazon_candidates (supplier_product_id, marketplace_id, compatibility_status, rank_position, asin);

create table if not exists public.wholesale_match_states (
    match_state_id uuid primary key default gen_random_uuid(),
    supplier_product_id uuid not null references public.wholesale_supplier_products(supplier_product_id) on delete cascade,
    marketplace_id text not null,
    match_status text not null default 'discovery_pending' check (match_status in (
        'discovery_pending', 'identity_review', 'eligibility_pending', 'matched',
        'restricted_no_eligible', 'no_candidates', 'error'
    )),
    selected_candidate_id uuid references public.wholesale_amazon_candidates(candidate_id) on delete set null,
    selection_source text not null default 'none' check (selection_source in ('none', 'automatic', 'manual')),
    identity_signature text,
    identity_changed boolean not null default false,
    rematch_requested boolean not null default false,
    selection_rationale jsonb not null default '{}'::jsonb check (jsonb_typeof(selection_rationale) = 'object'),
    last_discovered_at timestamptz,
    last_enriched_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (supplier_product_id, marketplace_id)
);

create index if not exists wholesale_match_states_queue_idx
    on public.wholesale_match_states (match_status, rematch_requested, updated_at);

create table if not exists public.wholesale_enrichment_runs (
    enrichment_run_id uuid primary key default gen_random_uuid(),
    supplier_id uuid references public.wholesale_suppliers(supplier_id) on delete cascade,
    marketplace_id text not null,
    run_status text not null default 'pending' check (run_status in ('pending', 'running', 'completed', 'completed_with_errors', 'failed', 'cancelled')),
    requested_limit integer not null check (requested_limit between 1 and 5000),
    processed_count integer not null default 0,
    matched_count integer not null default 0,
    review_count integer not null default 0,
    error_count integer not null default 0,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.wholesale_enrichment_work_items (
    work_item_id uuid primary key default gen_random_uuid(),
    enrichment_run_id uuid not null references public.wholesale_enrichment_runs(enrichment_run_id) on delete cascade,
    supplier_product_id uuid not null references public.wholesale_supplier_products(supplier_product_id) on delete cascade,
    work_status text not null default 'pending' check (work_status in ('pending', 'running', 'retry', 'completed', 'failed')),
    current_stage text not null default 'discovery' check (current_stage in ('discovery', 'catalog', 'keepa', 'eligibility', 'ranking', 'complete')),
    attempt_count integer not null default 0,
    lease_owner text,
    lease_expires_at timestamptz,
    error_summary text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz,
    unique (enrichment_run_id, supplier_product_id)
);

create index if not exists wholesale_enrichment_work_queue_idx
    on public.wholesale_enrichment_work_items (enrichment_run_id, work_status, lease_expires_at, created_at);

create or replace function public.wholesale_set_manual_candidate(
    p_supplier_product_id uuid,
    p_marketplace_id text,
    p_asin text,
    p_actor text default null
) returns public.wholesale_match_states
language plpgsql
security definer
set search_path = public
as $$
declare
    v_candidate public.wholesale_amazon_candidates;
    v_state public.wholesale_match_states;
begin
    if p_asin is null then
        insert into public.wholesale_match_states (
            supplier_product_id, marketplace_id, match_status, selected_candidate_id,
            selection_source, rematch_requested, selection_rationale
        ) values (
            p_supplier_product_id, p_marketplace_id, 'discovery_pending', null,
            'none', true, jsonb_build_object('cleared_by', p_actor)
        )
        on conflict (supplier_product_id, marketplace_id) do update set
            match_status = 'discovery_pending', selected_candidate_id = null,
            selection_source = 'none', rematch_requested = true,
            selection_rationale = jsonb_build_object('cleared_by', p_actor),
            updated_at = now()
        returning * into v_state;
        return v_state;
    end if;

    select * into v_candidate
    from public.wholesale_amazon_candidates
    where supplier_product_id = p_supplier_product_id
      and marketplace_id = p_marketplace_id
      and asin = upper(trim(p_asin));

    if not found then raise exception 'candidate_not_found'; end if;
    if v_candidate.compatibility_status <> 'compatible' then raise exception 'candidate_not_compatible'; end if;
    if v_candidate.eligibility_status <> 'eligible' or v_candidate.eligibility_expires_at <= now() then
        raise exception 'candidate_not_freshly_eligible';
    end if;

    update public.wholesale_amazon_candidates
    set match_sources = case when 'manual' = any(match_sources) then match_sources else array_append(match_sources, 'manual') end,
        updated_at = now()
    where candidate_id = v_candidate.candidate_id;

    insert into public.wholesale_match_states (
        supplier_product_id, marketplace_id, match_status, selected_candidate_id,
        selection_source, rematch_requested, selection_rationale, updated_at
    ) values (
        p_supplier_product_id, p_marketplace_id, 'matched', v_candidate.candidate_id,
        'manual', false, jsonb_build_object('selected_by', p_actor, 'asin', v_candidate.asin), now()
    )
    on conflict (supplier_product_id, marketplace_id) do update set
        match_status = excluded.match_status,
        selected_candidate_id = excluded.selected_candidate_id,
        selection_source = excluded.selection_source,
        rematch_requested = false,
        selection_rationale = excluded.selection_rationale,
        updated_at = now()
    returning * into v_state;
    return v_state;
end;
$$;

create or replace function public.wholesale_request_rematch(
    p_supplier_product_id uuid,
    p_marketplace_id text,
    p_actor text default null
) returns public.wholesale_match_states
language plpgsql
security definer
set search_path = public
as $$
declare v_state public.wholesale_match_states;
begin
    insert into public.wholesale_match_states (
        supplier_product_id, marketplace_id, match_status, rematch_requested, selection_rationale
    ) values (
        p_supplier_product_id, p_marketplace_id, 'discovery_pending', true,
        jsonb_build_object('requested_by', p_actor)
    )
    on conflict (supplier_product_id, marketplace_id) do update set
        match_status = 'discovery_pending', rematch_requested = true,
        selection_rationale = jsonb_build_object('requested_by', p_actor), updated_at = now()
    returning * into v_state;
    return v_state;
end;
$$;

create or replace view public.vw_wholesale_matching_products as
select
    p.supplier_product_id,
    p.supplier_id,
    p.identity_key,
    p.raw_title,
    p.raw_system,
    p.normalized_identifier,
    p.is_active,
    s.marketplace_id,
    coalesce(s.match_status, 'discovery_pending') as match_status,
    s.selection_source,
    c.asin as selected_asin,
    c.compatibility_status as selected_compatibility_status,
    c.eligibility_status as selected_eligibility_status,
    c.keepa_sales_rank_drops90,
    s.identity_changed,
    s.rematch_requested,
    s.updated_at as match_updated_at
from public.wholesale_supplier_products p
left join public.wholesale_match_states s on s.supplier_product_id = p.supplier_product_id
left join public.wholesale_amazon_candidates c on c.candidate_id = s.selected_candidate_id;

alter table public.wholesale_catalog_searches enable row level security;
alter table public.amazon_listing_eligibility_evidence enable row level security;
alter table public.wholesale_amazon_candidates enable row level security;
alter table public.wholesale_match_states enable row level security;
alter table public.wholesale_enrichment_runs enable row level security;
alter table public.wholesale_enrichment_work_items enable row level security;

revoke all on table public.wholesale_catalog_searches from anon, authenticated;
revoke all on table public.amazon_listing_eligibility_evidence from anon, authenticated;
revoke all on table public.wholesale_amazon_candidates from anon, authenticated;
revoke all on table public.wholesale_match_states from anon, authenticated;
revoke all on table public.wholesale_enrichment_runs from anon, authenticated;
revoke all on table public.wholesale_enrichment_work_items from anon, authenticated;
revoke all on table public.vw_wholesale_matching_products from anon, authenticated;
revoke all on function public.wholesale_set_manual_candidate(uuid, text, text, text) from public, anon, authenticated;
revoke all on function public.wholesale_request_rematch(uuid, text, text) from public, anon, authenticated;

grant select, insert, update, delete on table public.wholesale_catalog_searches to service_role;
grant select, insert, update, delete on table public.amazon_listing_eligibility_evidence to service_role;
grant select, insert, update, delete on table public.wholesale_amazon_candidates to service_role;
grant select, insert, update, delete on table public.wholesale_match_states to service_role;
grant select, insert, update on table public.wholesale_enrichment_runs to service_role;
grant select, insert, update, delete on table public.wholesale_enrichment_work_items to service_role;
grant select on table public.vw_wholesale_matching_products to service_role;
grant execute on function public.wholesale_set_manual_candidate(uuid, text, text, text) to service_role;
grant execute on function public.wholesale_request_rematch(uuid, text, text) to service_role;
