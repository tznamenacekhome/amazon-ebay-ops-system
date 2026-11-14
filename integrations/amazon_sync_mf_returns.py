"""Seller-fulfilled return report + canonical posted finances. Existing ECS/LWA only."""
import gzip
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

from amazon_mf import order_items
from amazon_mf_returns import REPORT_TYPE, financial_transaction, parse_report, windows, is_customer_order_id
from amazon_spapi_client import AmazonSPAPIClient
from sourcing_database_guard import wait_for_database

LOG = logging.getLogger('amazon_mf_returns')


def rpc(db, name, **args):
    return db.rpc(name, args).execute().data


def now():
    return datetime.now(timezone.utc)


def verify_order(db, client, account, order_id):
    if not is_customer_order_id(order_id):
        return False
    rows = db.table('amazon_mf_order_items').select('id').eq('account_id', account['id']).eq('amazon_order_id', order_id).limit(1).execute().data
    if rows:
        return True
    saved = db.table('amazon_sales_orders').select('fulfillment_channel,marketplace_id').eq('amazon_order_id', order_id).limit(1).execute().data
    if saved and (saved[0].get('fulfillment_channel') == 'AFN' or saved[0].get('marketplace_id') not in (None, account['marketplace_id'])):
        return False
    order = client.get_order(order_id)
    # order_items rejects marketplace/channel mismatches, including FBA.
    if (order.get('fulfillment') or {}).get('fulfilledBy') != 'MERCHANT':
        return False
    for item in order_items(order, account['marketplace_id']):
        rpc(db, 'mbop_mf_apply_order', p_account=account['id'], p_item=item)
    return bool(db.table('amazon_mf_order_items').select('id').eq('account_id', account['id']).eq('amazon_order_id', order_id).limit(1).execute().data)


def report(db, client, account, start, end):
    aid = account['id']
    previous = db.table('amazon_mf_return_reports').select('*').eq('account_id', aid).eq('window_start', start).order('requested_at', desc=True).limit(1).execute().data
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
        db.table('amazon_mf_return_reports').update({'status': status, 'source_created_at': source.get('createdTime'), 'document_id': source.get('reportDocumentId')}).eq('id', row['id']).execute()
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
    for line in lines:
        if not verify_order(db, client, account, line['amazon_order_id']):
            raise ValueError('Seller-fulfilled report order could not be verified against MF orders')
        rpc(db, 'mbop_mf_return_import', p_account=aid, p_report=row['id'], p_line=line)
    db.table('amazon_mf_return_reports').update({'status': 'IMPORTED', 'imported_at': now().isoformat(), 'error': None}).eq('id', row['id']).execute()
    return len(lines)


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


def synchronize(db, client, account):
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
    stats = {'returns': 0, 'financial_transactions': 0, 'packages_checked': 0, 'non_customer_financial_references': 0}
    errors = []
    for lower, higher in report_windows:
        try:
            stats['returns'] += report(db, client, account, lower, higher)
        except Exception as error:
            errors.append(str(error))
            LOG.warning('Return report coverage incomplete: %s', error)
    # Always overlap 59 days for delayed finance postings. No legacy/source totals are added.
    sources = transactions(client, start.isoformat(), end.isoformat())
    verified = {}
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
        oid = projected['amazon_order_id']
        if oid not in verified:
            try:
                verified[oid] = verify_order(db, client, account, oid)
            except Exception as error:
                verified[oid] = False
                message = f'Order {oid} verification failed: {error}'
                errors.append(message)
                LOG.warning('%s; continuing remaining transactions', message)
            finally:
                time.sleep(.5)
        if not verified[oid]:
            continue
        try:
            rpc(db, 'mbop_mf_return_finance', p_account=account['id'], p_transaction=projected, p_observed=end.isoformat())
            stats['financial_transactions'] += 1
        except Exception as error:
            message = f"Order {oid} transaction {projected['transaction_id']} import failed: {error}"
            errors.append(message)
            LOG.warning('%s; continuing remaining transactions', message)
    try:
        stats['packages_checked'] = sync_carriers(db, account)
    except Exception as error:
        errors.append(str(error))
    if errors:
        raise ValueError('; '.join(errors))
    return stats


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    db = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_ROLE_KEY'])
    run = None
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
        stats = synchronize(db, client, account)
        rpc(db, 'mbop_mf_return_sync_finish', p_run=run, p_error=None, p_stats=stats)
        LOG.info('MF returns synchronized: %s', stats)
        return 0
    except Exception as error:
        if run:
            rpc(db, 'mbop_mf_return_sync_finish', p_run=run, p_error=str(error)[:2000], p_stats={})
        else:
            db.table('amazon_mf_return_sync_runs').insert({'status': 'failed', 'finished_at': now().isoformat(), 'error': str(error)[:2000]}).execute()
        LOG.exception('MF return synchronization failed')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
