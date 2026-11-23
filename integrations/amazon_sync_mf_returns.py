"""Seller-fulfilled return report + canonical posted finances. Existing ECS/LWA only."""
import gzip
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

import requests
from dotenv import load_dotenv
from supabase import create_client

from amazon_mf import order_items
from amazon_mf_returns import REPORT_TYPE, financial_transaction, parse_report, windows, is_customer_order_id, explicitly_fba_transaction
from amazon_spapi_client import AmazonSPAPIClient
from sourcing_database_guard import wait_for_database

LOG = logging.getLogger('amazon_mf_returns')
MAX_PARTIAL_REPORTS = 6
MAX_FINANCE_RETRIES = 100


class OrderVerification(Enum):
    MF = 'merchant_fulfilled'
    FBA = 'amazon_fulfilled'
    UNVERIFIED = 'unverified'


class IncompleteReturnsSync(ValueError):
    def __init__(self, message, stats):
        super().__init__(message)
        self.stats = stats


def rpc(db, name, **args):
    return db.rpc(name, args).execute().data


def now():
    return datetime.now(timezone.utc)


def verify_order(db, client, account, order_id):
    if not is_customer_order_id(order_id):
        return OrderVerification.UNVERIFIED
    rows = db.table('amazon_mf_order_items').select('id').eq('account_id', account['id']).eq('amazon_order_id', order_id).limit(1).execute().data
    if rows:
        return OrderVerification.MF
    saved = db.table('amazon_sales_orders').select('fulfillment_channel,marketplace_id').eq('amazon_order_id', order_id).eq('marketplace_id', account['marketplace_id']).limit(1).execute().data
    if saved and saved[0].get('fulfillment_channel') == 'AFN':
        return OrderVerification.FBA
    order = client.get_order(order_id)
    if (order.get('salesChannel') or {}).get('marketplaceId') != account['marketplace_id']:
        raise ValueError(f'Order {order_id} marketplace mismatch')
    # order_items rejects marketplace/channel mismatches, including FBA.
    channel = (order.get('fulfillment') or {}).get('fulfilledBy')
    if channel == 'AMAZON':
        return OrderVerification.FBA
    if channel != 'MERCHANT':
        raise ValueError(f'Order {order_id} has missing/unknown fulfillment scope')
    for item in order_items(order, account['marketplace_id']):
        rpc(db, 'mbop_mf_apply_order', p_account=account['id'], p_item=item)
    if not db.table('amazon_mf_order_items').select('id').eq('account_id', account['id']).eq('amazon_order_id', order_id).limit(1).execute().data:
        raise ValueError(f'Merchant order {order_id} has no verified MF items')
    return OrderVerification.MF


def report(db, client, account, start, end, *, pending_report=None):
    aid = account['id']
    if pending_report is not None:
        if pending_report.get('account_id') != aid or not pending_report.get('report_id'):
            raise ValueError('Partial report has missing or mismatched account/report identity')
        row = pending_report.copy()
    else:
        previous = db.table('amazon_mf_return_reports').select('*').eq('account_id', aid).eq('window_start', start).neq('status', 'PARTIAL').order('requested_at', desc=True).limit(1).execute().data
        row = previous[0] if previous and previous[0].get('report_id') and previous[0]['status'] not in ('IMPORTED', 'FATAL', 'CANCELLED') else None
    if row is None:
        row = db.table('amazon_mf_return_reports').insert({'account_id': aid, 'window_start': start, 'window_end': end}).execute().data[0]
        response = client.create_report(REPORT_TYPE, data_start_time=start, data_end_time=end)
        if not response.get('reportId'):
            raise ValueError('Amazon createReport omitted reportId')
        row.update(report_id=response['reportId'], status='IN_QUEUE')
        db.table('amazon_mf_return_reports').update({'report_id': row['report_id'], 'status': 'IN_QUEUE'}).eq('id', row['id']).execute()
    deadline = time.monotonic() + 900
    while True:
        source = client.get_report(row['report_id'])
        status = source.get('processingStatus')
        # A failed/restarted retry must remain discoverable even if download/parsing fails.
        db.table('amazon_mf_return_reports').update({'status': 'PARTIAL' if row.get('status') == 'PARTIAL' else status, 'source_created_at': source.get('createdTime'), 'document_id': source.get('reportDocumentId')}).eq('id', row['id']).execute()
        if status in ('DONE', 'CANCELLED', 'FATAL'):
            break
        if time.monotonic() >= deadline:
            raise ValueError(f"Return report {row['report_id']} still {status}; next refresh resumes it")
        time.sleep(30)
    # CANCELLED is ambiguous (no data / explicit / throttled); never claim a successful empty import.
    if status != 'DONE':
        raise ValueError(f"Return report {row['report_id']}: {status}. Amazon can cancel an empty report; coverage remains unconfirmed.")
    document = client.get_report_document(source['reportDocumentId'])
    for attempt in range(3):
        try:
            response = requests.get(document['url'], timeout=120)
        except requests.RequestException:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise ValueError('Return report document transport failed after three attempts') from None
        if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
            time.sleep(2 ** attempt)
            continue
        if not response.ok:
            raise ValueError(f'Return report document download HTTP {response.status_code}')
        break
    content = gzip.decompress(response.content) if document.get('compressionAlgorithm') == 'GZIP' else response.content
    if len(content) > 20_000_000:
        raise ValueError('Return report exceeds bounded import size; narrow date window')
    lines = parse_report(content.decode('utf-8-sig'), os.getenv('BUSINESS_TIMEZONE', 'America/Los_Angeles'))
    if len(lines) > 5000:
        raise ValueError('Return report exceeds 5000 items; narrow date window')
    imported, fba_skipped, errors, verified = 0, 0, [], {}
    for line in lines:
        oid = line['amazon_order_id']
        try:
            if oid not in verified:
                try:
                    verified[oid] = verify_order(db, client, account, oid)
                except Exception as error:
                    verified[oid] = str(error)
                finally:
                    time.sleep(2)  # getOrder default rate: 0.5 requests/second.
            if verified[oid] == OrderVerification.FBA:
                fba_skipped += 1
                LOG.info('Skipping confirmed FBA report row: report=%s order=%s RMA=%s', row['report_id'], oid, line['rma'])
                continue
            if verified[oid] != OrderVerification.MF:
                raise ValueError(f'MF order verification incomplete: {verified[oid]}')
            rpc(db, 'mbop_mf_return_import', p_account=aid, p_report=row['id'], p_line=line)
            imported += 1
        except Exception as error:
            message = f"Report {row['report_id']} order {oid} RMA {line['rma']}: {error}"
            errors.append(message)
            LOG.warning('%s; retained report for retry, continuing remaining rows', message)
    if errors:
        message = '; '.join(errors)
        # Keep the original report/document identity resumable, never mark partial coverage IMPORTED.
        db.table('amazon_mf_return_reports').update({'status': 'PARTIAL', 'imported_at': None, 'error': message[:2000]}).eq('id', row['id']).execute()
        raise IncompleteReturnsSync(message, {'returns': imported, 'report_rows': len(lines)})
    db.table('amazon_mf_return_reports').update({'status': 'IMPORTED', 'imported_at': now().isoformat(), 'error': None}).eq('id', row['id']).execute()
    LOG.info('Return report imported: report=%s rows=%s MF_imported=%s FBA_skipped=%s; full returns sync not yet complete', row['report_id'], len(lines), imported, fba_skipped)
    return imported


def transactions(client, start, end, order_id=None):
    params = {'postedAfter': start, 'postedBefore': end}
    # Amazon explicitly requires omission of marketplaceId for US MFN.
    if order_id:
        params.update(relatedIdentifierName='ORDER_ID', relatedIdentifierValue=order_id)
    seen = set()
    for _ in range(50):
        response = client.request('GET', '/finances/2024-06-19/transactions', params=params)
        payload = response.get('payload', response)
        if not isinstance(payload.get('transactions'), list):
            raise ValueError('Transactions response missing list; coverage incomplete')
        yield from payload['transactions']
        token = payload.get('nextToken')
        if not token:
            return
        if token in seen:
            raise ValueError('Repeated finance pagination token')
        seen.add(token)
        params = {**params, 'nextToken': token}
        time.sleep(2)
    raise ValueError('Finance page budget exhausted; no successful checkpoint')


def apply_finance_work(db, client, account, work, verified, stats):
    """Replay a durable normalized payload; only acknowledge a verified outcome."""
    transaction = work['transaction_data']
    oid, tid = transaction['amazon_order_id'], work['transaction_id']
    phase = 'verification'
    try:
        if work['account_id'] != account['id']:
            raise ValueError('Finance work account mismatch')
        if work['status'] != 'pending':
            return None
        if oid not in verified:
            try:
                verified[oid] = verify_order(db, client, account, oid)
            except Exception as error:
                verified[oid] = error
            finally:
                time.sleep(2)
        outcome = verified[oid]
        if isinstance(outcome, Exception):
            raise outcome
        if outcome not in (OrderVerification.MF, OrderVerification.FBA):
            raise ValueError('Order remains unverified')
        phase = 'import'
        resolution = 'imported' if outcome == OrderVerification.MF else 'excluded_fba'
        applied = rpc(db, 'mbop_mf_return_finance_complete_work', p_account=account['id'],
                      p_transaction_id=tid, p_observed=work['observed_at'], p_resolution=resolution)
        if applied and resolution == 'imported':
            stats['financial_transactions'] += 1
        return None
    except Exception as error:
        message = f'Order {oid} transaction {tid} {phase} failed: {error}'
        # A failed attempt never deletes/acknowledges work. Its original payload
        # remains retryable even when its posted date leaves the rolling feed.
        db.table('amazon_mf_return_finance_work').update({'error': message[:2000], 'last_attempt_at': now().isoformat()}).eq('account_id', account['id']).eq('transaction_id', tid).eq('status', 'pending').execute()
        if len(stats['unresolved_financial_transactions']) < MAX_FINANCE_RETRIES:
            stats['unresolved_financial_transactions'].append({'order_id': oid, 'transaction_id': tid})
        LOG.warning('%s; durable work retained for retry', message)
        return message


def sync_carriers(db, account):
    """Reuse EasyPost tracker IDs, bounded to 50 active return packages / 10 creates."""
    from easypost_sync_shipments import create_tracker, retrieve_tracker, tracker_value, extract_delivered_time
    if not os.getenv('EASYPOST_API_KEY'):
        raise ValueError('Missing EASYPOST_API_KEY; return carrier first-scan/delivery synchronization unavailable')
    packages = db.table('amazon_mf_return_packages').select('*').eq('account_id', account['id']).is_('received_at', 'null').not_.is_('tracking_number', 'null').order('carrier_observed_at', nullsfirst=True).limit(50).execute().data
    created = 0
    errors = []
    for package in packages:
        try:
            if package.get('easypost_tracker_id'):
                tracker = retrieve_tracker(package['easypost_tracker_id'])
            elif created < 10:
                tracker = create_tracker(package['tracking_number'], package.get('carrier'))
                created += 1
            else:
                continue
            events = tracker_value(tracker, 'tracking_details') or []
            actual = [tracker_value(e, 'datetime') for e in events if tracker_value(e, 'status') in ('in_transit', 'out_for_delivery', 'delivered', 'available_for_pickup') and tracker_value(e, 'datetime')]
            updates = {'easypost_tracker_id': tracker_value(tracker, 'id'), 'carrier_status': tracker_value(tracker, 'status'), 'carrier_observed_at': now().isoformat(), 'carrier_error': None}
            if actual:
                updates['first_scan_at'] = min(actual)
            delivery = extract_delivered_time(tracker)
            if delivery:
                updates['carrier_delivery_at'] = delivery
            db.table('amazon_mf_return_packages').update(updates).eq('id', package['id']).execute()
        except Exception as error:
            errors.append(str(error))
            db.table('amazon_mf_return_packages').update({'carrier_error': str(error)[:1000], 'carrier_observed_at': now().isoformat()}).eq('id', package['id']).execute()
        time.sleep(.25)
    if errors:
        raise ValueError(f'{len(errors)} return tracker errors: {errors[0]}')
    return len(packages)


def synchronize(db, client, account, stats=None):
    if stats is None:
        stats = {}
    stats.update(returns=0, reports_imported=0, financial_transactions=0, packages_checked=0,
                 non_customer_financial_references=0, fba_financial_transactions_skipped=0,
                 unresolved_financial_transactions=[])
    end = now() - timedelta(minutes=3)
    # Daily-aligned windows permit resuming asynchronous reports after process failure.
    start = (end - timedelta(days=58)).replace(hour=0, minute=0, second=0, microsecond=0)
    upper = end.replace(second=0, microsecond=0)
    report_windows = list(windows(start, upper))
    # Revisit old open returns by their request dates rather than losing them to the rolling window.
    outstanding = db.table('vw_mf_open_returns').select('requested_at,amazon_order_id').eq('account_id', account['id']).neq('physical_status', 'inspected').order('requested_at').limit(501).execute().data
    if len(outstanding) > 500:
        raise ValueError('Over 500 open returns; date-window reconciliation needs review')
    for r in outstanding:
        if r.get('requested_at'):
            requested = datetime.fromisoformat(r['requested_at'])
            if requested < start:
                lower = requested.replace(hour=0, minute=0, second=0, microsecond=0)
                window = (lower.isoformat(), (lower + timedelta(days=1)).isoformat())
                if window not in report_windows:
                    report_windows.append(window)
    if len(report_windows) > 6:
        raise ValueError('More than six historical return windows require bounded reconciliation')
    errors = []
    # A row may fail before creating any normalized return. Discover persisted
    # partials independently of both normalized returns and the current date window.
    pending = db.table('amazon_mf_return_reports').select('*').eq('account_id', account['id']).eq('status', 'PARTIAL').order('requested_at').order('id').limit(MAX_PARTIAL_REPORTS + 1).execute().data
    stats['partial_reports_retried'] = 0
    if len(pending) > MAX_PARTIAL_REPORTS:
        errors.append(f'More than {MAX_PARTIAL_REPORTS} partial reports remain; bounded retry coverage incomplete')
    for row in pending[:MAX_PARTIAL_REPORTS]:
        try:
            stats['partial_reports_retried'] += 1
            stats['returns'] += report(db, client, account, row['window_start'], row['window_end'], pending_report=row)
            stats['reports_imported'] += 1
        except Exception as error:
            stats['returns'] += getattr(error, 'stats', {}).get('returns', 0)
            errors.append(str(error))
            LOG.warning('Persisted partial report %s remains unresolved: %s', row['id'], error)
    for lower, higher in report_windows:
        try:
            stats['returns'] += report(db, client, account, lower, higher)
            stats['reports_imported'] += 1
        except Exception as error:
            stats['returns'] += getattr(error, 'stats', {}).get('returns', 0)
            errors.append(str(error))
            LOG.warning('Return report coverage incomplete: %s', error)
    verified = {}
    pending_finances = db.table('amazon_mf_return_finance_work').select('*').eq('account_id', account['id']).eq('status', 'pending').order('created_at').order('transaction_id').limit(MAX_FINANCE_RETRIES + 1).execute().data
    stats['finance_work_retried'] = 0
    if len(pending_finances) > MAX_FINANCE_RETRIES:
        errors.append(f'More than {MAX_FINANCE_RETRIES} finance work items remain; bounded retry coverage incomplete')
    for work in pending_finances[:MAX_FINANCE_RETRIES]:
        stats['finance_work_retried'] += 1
        error = apply_finance_work(db, client, account, work, verified, stats)
        if error:
            errors.append(error)
    # Always overlap 59 days for newly posted finances, independently of durable retries.
    sources = transactions(client, start.isoformat(), end.isoformat())
    for source in sources:
        kind = str(source.get('transactionType') or '').lower()
        if kind not in ('refund', 'servicefee', 'adjustment', 'reimbursement'):
            continue
        projected = financial_transaction(source)
        if not projected['amazon_order_id']:
            continue  # Account-level charges cannot be assigned to an MF customer return.
        if not is_customer_order_id(projected['amazon_order_id']):
            stats['non_customer_financial_references'] += 1
            continue  # e.g. FBA shipment postage; outside the MF customer-return ledger.
        market = projected.get('marketplace_id')
        if market and market != account['marketplace_id']:
            continue
        if explicitly_fba_transaction(source):
            stats['fba_financial_transactions_skipped'] += 1
            LOG.info('Skipping explicit FBA finance transaction %s order %s (outside MF returns)',
                     projected['transaction_id'], projected['amazon_order_id'])
            continue
        try:
            # Write ahead of verification/import, so either failure and worker
            # interruption leave a replayable payload rather than an ID in logs.
            work = rpc(db, 'mbop_mf_return_finance_enqueue', p_account=account['id'],
                       p_transaction=projected, p_observed=end.isoformat())
        except Exception as error:
            message = f"Transaction {projected['transaction_id']} durable enqueue failed: {error}"
            errors.append(message)
            LOG.warning('%s', message)
            continue
        error = apply_finance_work(db, client, account, work, verified, stats)
        if error:
            errors.append(error)
    remaining = db.table('amazon_mf_return_finance_work').select('transaction_id').eq('account_id', account['id']).eq('status', 'pending').limit(1).execute().data
    if remaining:
        errors.append('Unresolved MF return finance work remains')
    try:
        stats['packages_checked'] = sync_carriers(db, account)
    except Exception as error:
        errors.append(str(error))
    if errors:
        raise IncompleteReturnsSync('; '.join(errors), stats)
    return stats


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    db = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
    run = None
    stats = {}
    try:
        wait_for_database(db, attempts=1)
        client = AmazonSPAPIClient.from_env()
        account = db.table('amazon_mf_accounts').select('*').eq('configured', True).single().execute().data
        if account['seller_id'] != client.config.seller_id or account['marketplace_id'] != client.config.marketplace_id:
            raise ValueError('MF returns seller/marketplace configuration mismatch')
        run = rpc(db, 'mbop_mf_return_sync_begin', p_account=account['id'])
        if not run:
            LOG.info('MF return synchronization already running')
            return 0
        stats = synchronize(db, client, account, stats=stats)
        rpc(db, 'mbop_mf_return_sync_finish', p_run=run, p_error=None, p_stats=stats)
        LOG.info('MF returns synchronized: %s', stats)
        return 0
    except Exception as error:
        if run:
            rpc(db, 'mbop_mf_return_sync_finish', p_run=run, p_error=str(error)[:2000], p_stats=stats)
        else:
            db.table('amazon_mf_return_sync_runs').insert({'status': 'failed', 'finished_at': now().isoformat(), 'error': str(error)[:2000]}).execute()
        LOG.error('MF returns sync failed; partial progress is not a successful checkpoint: %s', stats)
        LOG.exception('MF return synchronization failed')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
