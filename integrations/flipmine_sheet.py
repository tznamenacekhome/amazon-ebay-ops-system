"""Read-only Flipmine discovery input. Export fields never confirm a product match."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re

REQUIRED_HEADERS = ('asin', 'ebay item id')
MAX_ROWS = 10000
MAX_COLUMNS = 100
SHEET_SCOPE = 'https://www.googleapis.com/auth/spreadsheets.readonly'


def text(value):
    return '' if value is None else str(value).strip()


def parse_tab(values):
    """Return auditable nonblank rows, retaining row numbers and source evidence."""
    if not values:
        raise ValueError('Missing Flipmine column headers')
    headers = [text(value).casefold() for value in values[0]]
    if any(headers.count(name) != 1 for name in REQUIRED_HEADERS):
        raise ValueError('Flipmine headers must contain one ASIN and one eBay Item ID column')
    if len(values) - 1 > MAX_ROWS:
        raise ValueError('Flipmine tab exceeds the bounded row limit')
    parsed = []
    for number, cells in enumerate(values[1:], start=2):
        if not any(text(cell) for cell in cells):
            continue
        row = {name: cells[index] if index < len(cells) else None for index, name in enumerate(headers) if name}
        asin = text(row.get('asin')).upper()
        ebay_id = text(row.get('ebay item id'))
        if isinstance(row.get('ebay item id'), (float, int)):
            try:
                numeric = Decimal(ebay_id)
                if numeric.is_finite() and numeric == numeric.to_integral_value():
                    ebay_id = format(numeric, 'f').split('.')[0]
            except InvalidOperation:
                pass
        valid = bool(re.fullmatch(r'[A-Z0-9]{10}', asin) and re.fullmatch(r'[0-9]{9,15}', ebay_id))
        parsed.append({'row_number': number, 'asin': asin, 'ebay_legacy_item_id': ebay_id,
                       'status': 'pending' if valid else 'invalid',
                       'error': None if valid else 'Missing or invalid ASIN/eBay Item ID',
                       'source_evidence': {key: row.get(key) for key in
                           ('ebay title', 'amazon title', 'ebay price', 'date listed', 'asin', 'ebay item id')}})
    return parsed


def tab_fingerprint(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()


class FlipmineSheet:
    """Reuse MBOP's existing gspread/service-account authentication, with read scope."""
    def __init__(self):
        import gspread
        from sourcing_common import required_env
        self.spreadsheet_id = required_env('FLIPMINE_GOOGLE_SHEET_ID')
        credentials = os.getenv('GOOGLE_APPLICATION_CREDENTIALS') or os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
        if not credentials: raise RuntimeError('Existing Google service-account file is not configured')
        try:
            self.book = gspread.service_account(filename=credentials, scopes=[SHEET_SCOPE]).open_by_key(self.spreadsheet_id)
        except PermissionError as error:
            raise PermissionError('The existing MBOP Google service account needs Viewer access to the configured Flipmine sheet') from error

    def tabs(self):
        return [{'sheet_id': sheet.id, 'tab_name': sheet.title, 'worksheet': sheet}
                for sheet in self.book.worksheets()]

    def read(self, tab):
        sheet = tab['worksheet']
        if sheet.row_count > MAX_ROWS + 1 or sheet.col_count > MAX_COLUMNS:
            raise ValueError('Flipmine tab grid exceeds the bounded import size; trim unused rows/columns')
        from gspread.utils import rowcol_to_a1
        return sheet.get_values(f'A1:{rowcol_to_a1(sheet.row_count, sheet.col_count)}',
                                value_render_option='UNFORMATTED_VALUE')
