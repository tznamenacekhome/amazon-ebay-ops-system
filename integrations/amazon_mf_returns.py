"""Strict, non-PII projections for ordinary seller-fulfilled returns and finances."""
import csv
import hashlib
import io
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

REPORT_TYPE = 'GET_FLAT_FILE_RETURNS_DATA_BY_RETURN_DATE'


def is_customer_order_id(value):
    """Financial ORDER_ID references can also contain FBA shipment IDs.

    Ordinary Amazon customer order IDs use the documented 3-7-7 format.
    Never send a shipment/removal/account reference to the Orders endpoint.
    """
    return isinstance(value, str) and re.fullmatch(r'[0-9]{3}-[0-9]{7}-[0-9]{7}', value) is not None


def text(value):
    value = '' if value is None else str(value).strip()
    return None if value.lower() in ('', 'n/a', 'not available', 'null', '--') else value


def date(value, business_timezone='America/Los_Angeles'):
    value = text(value)
    if not value:
        return None
    value = value.replace('Z', '+00:00')
    parsed = None
    for fmt in (None, '%m/%d/%Y', '%m/%d/%Y %H:%M:%S', '%d-%b-%Y', '%Y-%m-%d %H:%M:%S'):
        try:
            parsed = datetime.fromisoformat(value) if fmt is None else datetime.strptime(value, fmt)
            break
        except ValueError:
            pass
    if parsed is None:
        raise ValueError(f'Unrecognized source date: {value}')
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo(business_timezone))).isoformat()


def amount(value):
    value = text(value)
    if value is None:
        return None
    result = Decimal(value.replace(',', ''))
    if not result.is_finite():
        raise ValueError('Nonfinite money')
    return str(result)


def windows(start, end):
    """Amazon allows at most 60 days/request. One-day overlap is intentional."""
    if start >= end:
        raise ValueError('Invalid report window')
    while start < end:
        upper = min(start + timedelta(days=59), end)
        yield start.isoformat(), upper.isoformat()
        if upper == end:
            break
        start = upper - timedelta(days=1)


def parse_report(content, business_timezone='America/Los_Angeles'):
    reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')), delimiter='\t')
    if not reader.fieldnames or not {'Order ID', 'Amazon RMA ID', 'Merchant SKU', 'Return quantity'}.issubset(reader.fieldnames):
        raise ValueError('Seller-fulfilled returns report headers missing')
    grouped = {}
    for row in reader:
        r = {k.strip(): text(v) for k, v in row.items() if k}
        order, rma, sku = r.get('Order ID'), r.get('Amazon RMA ID') or r.get('Merchant RMA ID'), r.get('Merchant SKU')
        if not order or not rma or not sku:
            raise ValueError('Return missing order/RMA/MSKU; cannot invent identity')
        item = r.get('Order Item ID')
        quantity = int(r.get('Return quantity') or '')
        if quantity < 0:
            raise ValueError('Negative return quantity')
        key = json.dumps([order, rma, item or sku], separators=(',', ':'))
        package = {'tracking_number': re.sub(r'[^A-Za-z0-9]', '', r.get('Tracking ID') or '').upper() or None,
                   'carrier': r.get('Return carrier'), 'delivery_at': date(r.get('Return delivery date'), business_timezone),
                   'delivery_raw': r.get('Return delivery date'), 'quoted_label_cost': amount(r.get('Label cost')),
                   'currency': r.get('Currency code'), 'label_type': r.get('Label type')}
        line = {'source_key': key, 'amazon_order_id': order, 'amazon_order_item_id': item, 'rma': rma,
                'merchant_rma': r.get('Merchant RMA ID'), 'seller_sku': sku, 'asin': r.get('ASIN'), 'title': r.get('Item Name'),
                'quantity': quantity, 'order_at': date(r.get('Order date'), business_timezone),
                'requested_at': date(r.get('Return request date'), business_timezone),
                'status': r.get('Return request status'), 'reason': r.get('Return Reason'), 'resolution': r.get('Resolution'),
                'reported_refund_amount': amount(r.get('Refunded Amount')), 'currency': r.get('Currency code'),
                'amazon_claim': {k: r.get(k) for k in ('SafeT Action reason', 'SafeT claim id', 'SafeT claim state', 'SafeT claim creation time', 'SafeT claim reimbursement amount', 'A-to-Z Claim')},
                'source_dates': {k: r.get(k) for k in ('Order date', 'Return request date', 'Return delivery date')},
                'packages': [], 'identity_warning': None}
        if key in grouped:
            line = grouped[key]
            if line['quantity'] != quantity:
                line['identity_warning'] = 'Report repeats item with different quantities; review package/item totals'
                line['quantity'] = max(line['quantity'], quantity)
        else:
            grouped[key] = line
        if package['tracking_number'] and package not in line['packages']:
            line['packages'].append(package)
    return list(grouped.values())


def identifier(rows, name, *, item=False):
    prefix = 'itemRelatedIdentifier' if item else 'relatedIdentifier'
    return next((text(r.get(prefix+'Value')) for r in rows or [] if r.get(prefix+'Name') == name), None)


def financial_transaction(transaction):
    """One canonical Transactions source. Report refund totals/legacy events never add to it."""
    tid = text(transaction.get('transactionId'))
    if not tid:
        raise ValueError('Financial transaction missing stable transactionId')
    order = identifier(transaction.get('relatedIdentifiers'), 'ORDER_ID')
    market = (transaction.get('marketplaceDetails') or {}).get('marketplaceId')
    total = transaction.get('totalAmount') or {}
    items = []
    for item in transaction.get('items') or []:
        refs = item.get('relatedIdentifiers') or []
        oid = identifier(refs, 'ORDER_ITEM_ID', item=True)
        adjustment = identifier(refs, 'ORDER_ADJUSTMENT_ITEM_ID', item=True)
        money = item.get('totalAmount') or {}
        # Do not pretend an adjustment-item ID is an order-item ID.
        items.append({'amazon_order_item_id': oid, 'adjustment_item_id': adjustment,
                      'amount': amount(money.get('currencyAmount')), 'currency': money.get('currencyCode'),
                      'components': item.get('breakdowns') or []})
    return {'transaction_id': tid, 'amazon_order_id': order, 'marketplace_id': market,
            'release_transaction_id': identifier(transaction.get('relatedIdentifiers'), 'RELEASE_TRANSACTION_ID'),
            'deferred_transaction_id': identifier(transaction.get('relatedIdentifiers'), 'DEFERRED_TRANSACTION_ID'),
            'kind': text(transaction.get('transactionType')), 'status': text(transaction.get('transactionStatus')),
            'posted_at': date(transaction.get('postedDate')), 'amount': amount(total.get('currencyAmount')),
            'currency': total.get('currencyCode'), 'description': text(transaction.get('description')),
            'items': items, 'components': transaction.get('breakdowns') or []}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
