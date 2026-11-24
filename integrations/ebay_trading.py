"""Read-only Trading transport. All production methods share one quota pool."""
from __future__ import annotations

import datetime as dt
import time
import xml.etree.ElementTree as ET

import requests

from ebay_browse_budget import production_budget, TRADING_RESOURCE, EbayQuotaPaused

NS = {'e': 'urn:ebay:apis:eBLBaseComponents'}
ENDPOINT = 'https://api.ebay.com/ws/api.dll'
READ_METHODS = {'GetItem', 'GetItemShipping', 'GetOrders', 'GetItemTransactions',
                'GetOrderTransactions', 'GetMyeBayBuying', 'GetUser', 'GetUserDisputes', 'GetDispute'}


def text(node, path, default=None):
    return node.findtext('/'.join('e:'+part for part in path.split('/')), default, NS) if node is not None else default


def elements(node, path):
    return node.findall('/'.join('e:'+part for part in path.split('/')), NS) if node is not None else []


class TradingError(RuntimeError):
    def __init__(self, codes, message='Trading could not supply listing evidence'):
        super().__init__(message)
        self.codes = codes


def post(url=ENDPOINT, *, headers, data, timeout=60, priority='essential', **kwargs):
    """Preserve operational clients' response contracts; never accept mutations."""
    method = next((v for k, v in headers.items() if k.lower() == 'x-ebay-api-call-name'), '')
    if url != ENDPOINT or method not in READ_METHODS:
        raise ValueError('Shared Trading transport only permits documented read methods')
    gate = production_budget()
    from ebay_sourcing_search import retry_after_seconds
    for attempt in range(1, 4):
        if gate:
            gate.reserve(TRADING_RESOURCE, operation=method, priority=priority)
        try:
            response = requests.post(url, headers=headers, data=data, timeout=timeout, **kwargs)
        except requests.RequestException:
            if attempt == 3:
                if gate:raise gate.block(TRADING_RESOURCE,'provider_transport_failure') from None
                raise TradingError([], 'Trading transport unavailable') from None
            time.sleep(retry_after_seconds(None, attempt))
            continue
        try:
            root = ET.fromstring(response.content)
            errors = elements(root, 'Errors')
            codes = [text(e, 'ErrorCode') for e in errors if text(e, 'SeverityCode') != 'Warning']
        except (ET.ParseError,TypeError):
            root, errors, codes = None, [], []
        if response.status_code == 429 or '518' in codes:
            delay = retry_after_seconds(response, attempt)
            if gate:
                # Record only public error metadata, never the request/auth XML.
                safe = requests.Response(); safe.status_code = response.status_code; safe.headers = response.headers
                import json
                safe._content = json.dumps({'errors': [{'errorId': text(e, 'ErrorCode'), 'message': text(e, 'ShortMessage')} for e in errors]}).encode()
                pause = gate.after_429(safe, delay, TRADING_RESOURCE, exhausted='518' in codes)
                gate.event('rate_limit', TRADING_RESOURCE)
                if pause.retry_at and dt.datetime.fromisoformat(pause.retry_at.replace('Z','+00:00')) > dt.datetime.now(dt.UTC)+dt.timedelta(seconds=60):
                    raise pause
            else:
                pause = EbayQuotaPaused('Trading call usage limit', resource=TRADING_RESOURCE)
            if attempt == 3:
                raise pause
            time.sleep(delay)
            continue
        if response.status_code >= 500:
            if attempt == 3:
                if gate:raise gate.block(TRADING_RESOURCE,'provider_server_failure',response.status_code)
                raise TradingError([], 'Trading server unavailable')
            time.sleep(retry_after_seconds(response, attempt))
            continue
        if gate and any(text(e,'ErrorClassification')=='SystemError' for e in errors):
            raise gate.block(TRADING_RESOURCE,'provider_api_system_failure',response.status_code)
        if response.status_code in (401,403) and gate:
            raise gate.block(TRADING_RESOURCE,'provider_authorization_failure',response.status_code)
        response.raise_for_status()
        return response
    raise TradingError([], 'Trading request did not complete')


def call(token, method, fields, *, priority=None):
    from xml.sax.saxutils import escape
    body = (f'<?xml version="1.0" encoding="utf-8"?><{method}Request xmlns="{NS["e"]}">'
            f'<RequesterCredentials><eBayAuthToken>{escape(token)}</eBayAuthToken></RequesterCredentials>'
            f'{fields}</{method}Request>')
    response = post(headers={'X-EBAY-API-CALL-NAME':method, 'X-EBAY-API-COMPATIBILITY-LEVEL':'1423',
                             'X-EBAY-API-SITEID':'0', 'X-EBAY-API-IAF-TOKEN':token, 'Content-Type':'text/xml'},
                    data=body, priority=priority)
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        raise TradingError([], 'Invalid Trading response') from None
    if text(root, 'Ack') not in ('Success', 'Warning'):
        raise TradingError([text(e, 'ErrorCode') for e in elements(root, 'Errors')])
    return root
