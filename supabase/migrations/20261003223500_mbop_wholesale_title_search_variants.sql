begin;

alter table public.wholesale_catalog_searches
    drop constraint if exists wholesale_catalog_searches_query_type_check;

alter table public.wholesale_catalog_searches
    add constraint wholesale_catalog_searches_query_type_check
    check (query_type in ('identifier', 'title_platform', 'title'));

comment on column public.wholesale_catalog_searches.query_type is
    'Amazon Catalog discovery branch: exact identifier, title with platform, or bounded title-only fallback.';

commit;
