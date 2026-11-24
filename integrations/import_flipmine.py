"""Manual Flipmine discovery -> existing MBOP sourcing evaluation. No scheduled entry point."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import logging
import os
import re
import uuid
import time
import requests
from types import SimpleNamespace

from flipmine_sheet import FlipmineSheet, parse_tab, tab_fingerprint
from flipmine_context import SourcingContext
from sourcing_common import get_supabase_client, fetch_settings
from sourcing_database_guard import wait_for_database
from run_sourcing_workflow import refresh_buyer_offer_history
from ebay_sourcing_search import get_access_token, get_with_retries, end_user_context_header, map_item, is_allowed_candidate, EBAY_BROWSE_ITEM_URL, EbayRateLimitedError
from ebay_browse_budget import production_budget, EbayQuotaPaused
from score_sourcing_opportunities import (fetch_matching_context, fetch_historical_status_by_key,
    fetch_keepa_price_context_by_asin, fetch_owned_units_by_asin, score_candidate_batches, snapshot_new_opportunities)
from cleanup_sourcing_duplicate_asin_opportunities import enforce_one_open_opportunity_per_asin
from refresh_sourcing_listing_availability import listing_is_available

LOG = logging.getLogger('flipmine')
NAMESPACE = uuid.UUID('68d9a519-ff4c-4091-8f98-0fa486fa2551')
TERMINAL = {'invalid', 'evaluated', 'duplicate', 'excluded'}


def now(): return dt.datetime.now(dt.UTC).isoformat()
def rpc(db, name, **args): return db.rpc(name, args).execute().data


def safe_error(error):
    message = f'{type(error).__name__}: {error}'
    message = re.sub(r'(?i)(key|token|secret|password|authorization)=([^&\s]+)', r'\1=[redacted]', message)
    for name, value in os.environ.items():
        if value and len(value) > 10 and any(term in name for term in ('TOKEN', 'SECRET', 'PASSWORD', 'API_KEY', 'CREDENTIALS', 'FLIPMINE_GOOGLE_SHEET_ID')):
            message = message.replace(value, '[redacted]')
    return message[:1500]


def read_rows(db, tab_id):
    rows = []
    for offset in range(0, 10001, 500):
        page = db.table('sourcing_flipmine_rows').select('*').eq('tab_id', tab_id).order('row_number').range(offset, offset+499).execute().data or []
        rows.extend(page)
        if len(page) < 500: return rows
    raise ValueError('Flipmine persisted row bound exceeded')


class ListingUnavailable(ValueError): pass


def fetch_listing(token, legacy_id, settings):
    response, _metrics = get_with_retries(f'{EBAY_BROWSE_ITEM_URL}/get_item_by_legacy_id', call_type='detail',
        headers={'Authorization': f'Bearer {token}', 'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US',
                 'X-EBAY-C-ENDUSERCTX': end_user_context_header(settings)},
        params={'legacy_item_id': legacy_id, 'quantity_for_shipping_estimate': '1'}, timeout=30)
    if response.status_code in (404, 410): raise ListingUnavailable('eBay listing no longer available')
    if not response.ok: raise RuntimeError(f'eBay listing detail HTTP {response.status_code}')
    item = response.json()
    if item.get('legacyItemId') != legacy_id or not item.get('title') or not item.get('itemId'):
        raise ValueError('eBay returned missing or mismatched listing identity')
    available, reason = listing_is_available(item)
    if not available: raise ListingUnavailable(reason)
    # A parent export does not identify a purchasable variation. Never choose one by ASIN/title.
    if item.get('itemGroupHref') and str(item.get('itemId')).endswith('|0'):
        raise ValueError('Variation listing requires a specific variation; retained for review')
    return item


class FlipmineImporter:
    def __init__(self, db, run_id, sheet, *, context=None, listing_fetch=None):
        self.db, self.run_id, self.sheet = db, run_id, sheet
        self.settings = fetch_settings(db)
        self.context = context or SourcingContext(db, self.settings)
        self.listing_fetch = listing_fetch or fetch_listing
        self.token = None
        self.listings = {}
        self.listing_errors = {}
        self.deadline = None
        self.resume_only = False
        self.matching = self.history = None

    def evaluation_context(self):
        if self.matching is None:
            refresh_buyer_offer_history(None)
            self.matching=fetch_matching_context(self.db)
            self.history=fetch_historical_status_by_key(self.db)

    def heartbeat(self):
        updated = self.db.table('sourcing_flipmine_runs').update({'heartbeat_at': now()}).eq('run_id', self.run_id).eq('status', 'running').execute().data
        if not updated: raise RuntimeError('Flipmine worker lease lost')

    def row_update(self, tab_id, row, **values):
        rpc(self.db, 'flipmine_update_row', p_run=self.run_id, p_tab=tab_id, p_row=row['row_number'], p_values=values)
        row.update(values)

    def process_row(self, tab, row):
        tab_id, asin = tab['tab_id'], row['asin']
        proposed_id = f"v1|{row['ebay_legacy_item_id']}|0"
        # Already-evaluated exact pairs only gain provenance; no duplicate decisions or hold changes.
        existing = self.db.table('sourcing_ebay_candidates').select('*').eq('asin', asin).eq('ebay_item_id', proposed_id).limit(1).execute().data or []
        if existing:
            opportunities = self.db.table('sourcing_opportunities').select('opportunity_id,matching_diagnostics_json').eq('candidate_id', existing[0]['candidate_id']).eq('asin', asin).limit(1).execute().data or []
            if opportunities:
                rpc(self.db, 'flipmine_bind_candidate', p_run=self.run_id, p_tab=tab_id, p_row=row['row_number'], p_candidate=existing[0])
                return 'duplicate'
        seed = self.context.seed(asin)
        if not seed:
            self.row_update(tab_id, row, status='excluded', error='Excluded by existing catalog eligibility, inventory/velocity or blocked-ASIN rules')
            return 'excluded'
        seed = {**seed, 'sourcing_run_id': tab['sourcing_run_id'],
                'seed_id': str(uuid.uuid5(NAMESPACE, f"{tab_id}:{asin}"))}
        self.db.table('sourcing_seed_asins').upsert(seed, on_conflict='seed_id').execute()
        legacy_id = row['ebay_legacy_item_id']
        if legacy_id in self.listing_errors: raise self.listing_errors[legacy_id]
        if legacy_id not in self.listings:
            if self.token is None: self.token = get_access_token()
            try: self.listings[legacy_id] = self.listing_fetch(self.token, legacy_id, self.settings)
            except Exception as error:
                self.listing_errors[legacy_id]=error
                raise
        item = self.listings[legacy_id]
        candidate = map_item(seed, item)
        if not is_allowed_candidate(candidate, item, self.settings, seed):
            self.row_update(tab_id, row, status='excluded', error='Excluded by existing sourcing location, pickup or platform discovery rules')
            return 'excluded'
        candidate['candidate_id'] = str(uuid.uuid5(NAMESPACE, f"{candidate['ebay_item_id']}:{asin}"))
        bound = rpc(self.db, 'flipmine_bind_candidate', p_run=self.run_id, p_tab=tab_id,
                    p_row=row['row_number'], p_candidate=candidate)
        if bound['duplicate']: return 'duplicate'
        candidate['candidate_id'] = bound['candidate']['candidate_id']
        prices = fetch_keepa_price_context_by_asin(self.db, [asin])
        owned = fetch_owned_units_by_asin(self.db, [seed])
        self.evaluation_context()
        # This is the production matcher, seller/history/offer/hold/economic evaluator.
        scored = list(score_candidate_batches(self.db, [candidate], {seed['seed_id']: seed}, self.settings,
                      prices, self.history, self.matching, owned))[0]
        if not scored: raise RuntimeError('Shared sourcing evaluator returned no decision')
        diagnostics = scored['matching_diagnostics_json']
        if not diagnostics.get('hard_rule_pass', False):
            # Normal Browse discovery discards matching_reject before opportunity persistence.
            self.row_update(tab_id, row, status='excluded', evaluation=diagnostics, error='Blocked by existing MBOP match rules')
            return 'excluded'
        rpc(self.db, 'flipmine_write_opportunity', p_run=self.run_id, p_tab=tab_id, p_row=row['row_number'], p_scored=scored)
        return 'evaluated'

    def process_tab(self, source):
        tab = rpc(self.db, 'flipmine_claim_tab', p_run=self.run_id, p_spreadsheet=self.sheet.spreadsheet_id,
                  p_sheet=source['sheet_id'], p_name=source['tab_name'])
        if tab is None: return None
        tab_id = tab['tab_id']
        try:
            if not tab.get('source_hash'):
                values = self.sheet.read(source)
                rpc(self.db, 'flipmine_snapshot_tab', p_run=self.run_id, p_tab=tab_id,
                    p_hash=tab_fingerprint(values), p_rows=parse_tab(values))
            rows = read_rows(self.db, tab_id)
            self.progress(tab_id,rows)
            if any(row['status'] not in TERMINAL for row in rows):
                budget=production_budget()
                if budget: budget.check()  # Before spending Amazon/Keepa resources on an exhausted feed.
                self.evaluation_context()
            for index, row in enumerate(rows):
                if row['status'] in TERMINAL: continue
                self.heartbeat()
                if self.deadline and time.monotonic()>=self.deadline:
                    raise EbayQuotaPaused('checkpoint continuation',(dt.datetime.now(dt.UTC)+dt.timedelta(seconds=5)).isoformat(),'checkpoint')
                if index % 20 == 0: wait_for_database(self.db)
                try:
                    row['status'] = self.process_row(tab, row)
                except (EbayRateLimitedError,EbayQuotaPaused):
                    # This is unprocessed work, not a rejected product or failed row.
                    self.progress(tab_id,rows)
                    raise
                except ListingUnavailable as error:
                    self.row_update(tab_id, row, status='excluded', error=safe_error(error))
                except Exception as error:
                    self.row_update(tab_id, row, status='failed', error=safe_error(error))
                    LOG.warning('flipmine_row_failed %s', json.dumps({'run': self.run_id, 'tab': tab_id,
                                'row': row['row_number'], 'asin': row['asin'], 'ebay_item_id': row['ebay_legacy_item_id'],
                                'reason': safe_error(error)}))
                if index % 20 == 0:
                    self.progress(tab_id,rows)
            # Reuse normal persistence-side duplicate-ASIN and initial audit-snapshot policies.
            enforce_one_open_opportunity_per_asin(self.db)
            snapshot_new_opportunities(self.db, tab['sourcing_run_id'])
            summary = rpc(self.db, 'flipmine_tab_evaluated', p_run=self.run_id, p_tab=tab_id)
            LOG.info('flipmine_tab_evaluated %s', json.dumps({'run': self.run_id, 'tab': tab_id, **summary}))
            return summary
        except (EbayRateLimitedError,EbayQuotaPaused): raise
        except Exception as error:
            self.db.table('sourcing_flipmine_tabs').update({'status': 'partial', 'error_summary': safe_error(error)}).eq('tab_id', tab_id).eq('run_id', self.run_id).execute()
            raise

    def progress(self,tab_id,rows):
        counts={key:sum(r['status']==key for r in rows) for key in ('evaluated','duplicate','invalid','excluded','failed','pending')}
        counts['duplicates']=counts.pop('duplicate');counts['rows']=len(rows)
        self.db.table('sourcing_flipmine_tabs').update({'summary':counts}).eq('tab_id',tab_id).eq('run_id',self.run_id).eq('status','running').execute()
        self.db.table('sourcing_flipmine_runs').update({'summary':{'phase':'processing'}}).eq('run_id',self.run_id).eq('status','running').execute()

    def run(self):
        results, failures = [], []
        sources = list(self.sheet.tabs())
        known = {s['sheet_id'] for s in sources}
        retained = [] if getattr(self,'resume_only',False) else self.db.table('sourcing_flipmine_tabs').select('sheet_id,tab_name,source_hash').eq('spreadsheet_id', self.sheet.spreadsheet_id).neq('status', 'completed').execute().data or []
        for source in retained:
            if source['sheet_id'] not in known:
                sources.append(source)  # Durable snapshots survive source-tab removal/rename.
        for source in sources:
            self.heartbeat()
            try:
                summary = self.process_tab(source)
                if summary is not None:
                    results.append(summary)
                    if summary['failed']: failures.append('Some rows require retry')
            except (EbayRateLimitedError,EbayQuotaPaused) as error:
                retry=getattr(error,'retry_at',None) or (dt.datetime.now(dt.UTC)+dt.timedelta(minutes=5)).isoformat()
                rpc(self.db,'flipmine_pause',p_run=self.run_id,p_until=retry,p_resource=getattr(error,'resource','buy.browse'),p_reason=safe_error(error))
                LOG.warning('FLIPMINE_PAUSED run=%s retry_at=%s reason=%s',self.run_id,retry,safe_error(error))
                return 0
            except Exception as error:
                failures.append(safe_error(error))
        status = 'partial' if failures else 'evaluated' if results else 'completed'
        self.db.table('sourcing_flipmine_runs').update({'status': status, 'completed_at': now(),
            'summary': {'tabs': len(results), 'no_new_tabs': not results and not failures},
            'error_summary': '; '.join(failures)[:2000] or None}).eq('run_id', self.run_id).eq('status', 'running').execute()
        return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id')
    parser.add_argument('--resume-run-id',help='Resume only this saved import; never discover Google tabs')
    parser.add_argument('--resume-due',action='store_true',help='Existing scheduler: claim one due saved checkpoint only')
    parser.add_argument('--max-seconds',type=int,default=0)
    parser.add_argument('--plan', action='store_true', help='Read source metadata/headers only; no provider requests or DB writes')
    args = parser.parse_args()
    from sourcing_common import load_environment
    load_environment()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    db = None
    try:
        if args.resume_run_id or args.resume_due:
            db=get_supabase_client()
            args.run_id=rpc(db,'flipmine_claim_resume',p_run=args.resume_run_id,p_due_only=not bool(args.resume_run_id))
            if not args.run_id:
                LOG.info('No due Flipmine checkpoint; no discovery or provider calls')
                return 0
            task_arn=os.getenv('ECS_TASK_ARN')
            metadata=os.getenv('ECS_CONTAINER_METADATA_URI_V4')
            if metadata:
                try:
                    task_response=requests.get(metadata+'/task',timeout=3)
                    task_response.raise_for_status()
                    task_arn=task_response.json().get('TaskARN')
                except (requests.RequestException,ValueError):
                    LOG.warning('Current ECS task metadata unavailable; clearing stale worker reference')
            db.table('sourcing_flipmine_runs').update({'task_arn':task_arn}).eq('run_id',args.run_id).eq('status','running').execute()
            tabs=db.table('sourcing_flipmine_tabs').select('sheet_id,tab_name,spreadsheet_id,source_hash').eq('run_id',args.run_id).neq('status','completed').execute().data or []
            if not tabs or any(not t.get('source_hash') for t in tabs): raise ValueError('Saved tab snapshot incomplete; manual review required')
            sheet=SimpleNamespace(spreadsheet_id=tabs[0]['spreadsheet_id'],tabs=lambda:tabs)
            wait_for_database(db)
        elif not args.plan:
            if not args.run_id: raise ValueError('--run-id is required for a manual import')
            uuid.UUID(args.run_id)
            db = get_supabase_client()
            wait_for_database(db)
        if not (args.resume_run_id or args.resume_due): sheet = FlipmineSheet()
        if args.plan:
            for source in sheet.tabs():
                rows = parse_tab(sheet.read(source))
                print(json.dumps({'tab_name': source['tab_name'], 'sheet_id': source['sheet_id'],
                                  'rows': len(rows), 'valid': sum(r['status'] == 'pending' for r in rows)}))
            return 0
        worker=FlipmineImporter(db,args.run_id,sheet)
        worker.resume_only=bool(args.resume_run_id or args.resume_due)
        worker.deadline=time.monotonic()+args.max_seconds if args.max_seconds else None
        return worker.run()
    except Exception as error:
        if db is not None and args.run_id:
            db.table('sourcing_flipmine_runs').update({'status': 'failed', 'completed_at': now(),
                'error_summary': safe_error(error)}).eq('run_id', args.run_id).eq('status', 'running').execute()
        LOG.error('Flipmine import failed: %s', safe_error(error))
        return 1


if __name__ == '__main__': raise SystemExit(main())
