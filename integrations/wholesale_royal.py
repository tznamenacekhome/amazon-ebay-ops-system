"""Pure, bounded Royal price-list parser. No marketplace or database calls."""
from __future__ import annotations

import hashlib
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook

PARSER_VERSION = "royal-v1"
SUPPLIER_KEY = "royal-electronics"
MAX_ROWS = 10000
MAX_PRODUCTS = 5000
USED = re.compile(r"\bUSED\b", re.IGNORECASE)
DATE_LABEL = re.compile(
    r"(?:price\s*list\s*(?:effective\s*)?date|effective\s*date)\s*[:=]\s*"
    r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE
)
EXPECTED_HEADERS = ["ORDER", "TITLE", "SYS", "UPC / SKU", "PRICE", "QTY", "SUB"]


def identity_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def identifier_metadata(raw: str) -> dict:
    """Remove only whitespace/hyphens from digit-shaped codes; never repair digits."""
    stripped = raw.strip()
    normalized = re.sub(r"[\s-]", "", stripped) if re.fullmatch(r"[0-9\s-]+", stripped) else stripped
    kind = "supplier_sku"
    valid = None
    status = "non_barcode"
    if re.fullmatch(r"[0-9]+", normalized):
        if len(normalized) in (12, 13):
            kind = "upc_a" if len(normalized) == 12 else "ean_13"
            total = sum(int(d) * (3 if i % 2 == 0 else 1)
                        for i, d in enumerate(reversed(normalized[:-1])))
            valid = (10 - total % 10) % 10 == int(normalized[-1])
            status = "valid" if valid else "invalid_check_digit"
        else:
            kind, status = "unconfirmed_numeric", "unexpected_length"
    return {"normalized_identifier": normalized, "identifier_type": kind,
            "identifier_length": len(normalized), "check_digit_valid": valid,
            "identifier_status": status}


def product_identity(title: str, system: str, normalized_identifier: str) -> str:
    # Title is part of identity because Royal does not supply a proven stable offer SKU.
    # Delimited JSON avoids ambiguous concatenation; no fuzzy matching or platform inference.
    parts = [identity_text(normalized_identifier), identity_text(system), identity_text(title)]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def raw_text(value) -> str:
    return "" if value is None else str(value)


def availability(raw: str) -> dict:
    match = re.fullmatch(r"\s*([0-9]+)\s*(\+)?\s*", raw)
    if not match or int(match[1]) > 2147483647:
        return {"availability_min": None, "availability_is_exact": None}
    return {"availability_min": int(match[1]), "availability_is_exact": not bool(match[2])}


def supplier_price(value) -> str:
    if isinstance(value, bool):
        raise ValueError("Price is not a monetary value")
    text = str(value).strip()
    if not re.fullmatch(r"\$?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,2})?", text):
        raise ValueError("Price must be a nonnegative USD amount with at most two decimals")
    try:
        amount = Decimal(text.replace("$", "").replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("Invalid price") from exc
    if amount > Decimal("9999999999.99"):
        raise ValueError("Price exceeds storage limit")
    return format(amount.quantize(Decimal("0.01")), "f")


def parse_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}T.*", text):
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ValueError("Price-list date must be YYYY-MM-DD or MM/DD/YYYY")


def filename_effective_date(filename: str, reference_date: date | datetime | str | None = None) -> date | None:
    """Accept only unambiguous dates in a supplier-looking filename."""
    stem = Path(filename).stem
    if not re.search(r"royal|price|list", stem, re.IGNORECASE):
        return None
    matches = []
    for pattern, fmt in (
        (r"(?<!\d)(20\d{2}[-_]?\d{2}[-_]?\d{2})(?!\d)", None),
        (r"(?<!\d)(\d{1,2}[-_]\d{1,2}[-_]20\d{2})(?!\d)", "%m-%d-%Y"),
        (r"(?<!\d)(\d{7,8})(?!\d)", "compact_us"),
    ):
        for match in re.findall(pattern, stem):
            try:
                value = match.replace("_", "-")
                if fmt == "compact_us":
                    month_digits = 1 if len(value) == 7 else 2
                    matches.append(date(int(value[-4:]), int(value[:month_digits]), int(value[month_digits:month_digits + 2])))
                else:
                    matches.append(datetime.strptime(value, fmt or ("%Y-%m-%d" if "-" in value else "%Y%m%d")).date())
            except ValueError:
                continue
    if not matches and reference_date is not None:
        reference = parse_date(reference_date)
        for month, day in re.findall(r"(?<!\d)(\d{1,2})[-_](\d{1,2})(?![-_\d])", stem):
            candidates = []
            for year in (reference.year - 1, reference.year, reference.year + 1):
                try:
                    candidates.append(date(year, int(month), int(day)))
                except ValueError:
                    pass
            if candidates:
                nearest = min(candidates, key=lambda value: abs((value - reference).days))
                if abs((nearest - reference).days) <= 45:
                    matches.append(nearest)
    unique = set(matches)
    if len(unique) > 1:
        raise ValueError("Conflicting dates in supplier filename")
    return next(iter(unique)) if unique else None


def effective_date(workbook, sheet, explicit: date | str | None) -> tuple[date, str]:
    found = set()
    defined = workbook.defined_names.get("PRICE_LIST_DATE")
    if defined:
        for sheet_name, coordinate in defined.destinations:
            found.add(parse_date(workbook[sheet_name][coordinate].value))
    texts = [workbook.properties.title, workbook.properties.subject, workbook.properties.description]
    texts.extend(str(getattr(sheet, name)) for name in (
        "oddHeader", "evenHeader", "firstHeader", "oddFooter", "evenFooter", "firstFooter"))
    # Only explicitly labelled document dates qualify; product dates and Excel &D do not.
    texts.extend(raw_text(cell.value) for row in sheet.iter_rows(max_col=7) for cell in row)
    for text in texts:
        for match in DATE_LABEL.finditer(text or ""):
            found.add(parse_date(match[1]))
    if len(found) > 1:
        raise ValueError("Conflicting document dates; correct the workbook metadata")
    supplied = parse_date(explicit) if explicit is not None else None
    if found:
        detected = next(iter(found))
        if supplied and supplied != detected:
            raise ValueError("Explicit date conflicts with supplier document date")
        return detected, "supplier_document"
    if supplied:
        return supplied, "operator_parameter"
    raise ValueError("No reliable supplier document date; provide --effective-date YYYY-MM-DD")


def parse_workbook(path: str | Path, price_list_date: date | str | None = None) -> dict:
    path = Path(path)
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("Workbook exceeds 10 MiB limit")
    content = path.read_bytes()
    with ZipFile(BytesIO(content)) as archive:
        if sum(info.file_size for info in archive.infolist()) > 50 * 1024 * 1024:
            raise ValueError("Expanded workbook exceeds 50 MiB limit")
    workbook = load_workbook(BytesIO(content), data_only=False, keep_links=False)
    try:
        sheet = next((workbook[name] for name in ("COMPLETE LIST", "Price List")
                      if name in workbook.sheetnames and
                      [raw_text(workbook[name].cell(1, col).value).strip().upper() for col in range(1, 8)] == EXPECTED_HEADERS), None)
        if sheet is None:
            raise ValueError("Required Royal full-list sheet and headers are missing")
        if sheet.max_row > MAX_ROWS or sheet.max_column > 50:
            raise ValueError("Workbook exceeds bounded parser dimensions")
        headers = [raw_text(sheet.cell(1, col).value).strip().upper() for col in range(1, 8)]
        if headers != EXPECTED_HEADERS:
            raise ValueError("Expected Royal row-1 headers in columns A:G")
        dated, date_source = effective_date(workbook, sheet, price_list_date)
        date_cells = set()
        if workbook.defined_names.get("PRICE_LIST_DATE"):
            date_cells = {coordinate.replace("$", "") for name, coordinate in
                          workbook.defined_names["PRICE_LIST_DATE"].destinations if name == sheet.title}
        summary = Counter({key: 0 for key in (
            "rows_encountered", "rows_imported", "used_rows_skipped", "non_product_rows_skipped",
            "invalid_rows_skipped", "duplicate_rows_skipped", "conflict_rows_skipped",
            "identifier_warnings", "availability_warnings")})
        systems = Counter()
        warnings, errors, source_rows = [], [], []
        grouped = defaultdict(list)
        for number, cells in enumerate(sheet.iter_rows(min_row=2, max_col=7), 2):
            title, system, identifier, price, qty = cells[1:6]
            values = [c.value for c in cells[1:6]]
            source = {"row_number": number, "values": [raw_text(v) for v in values],
                      "cell_types": [c.data_type for c in cells[1:6]],
                      "identifier_number_format": identifier.number_format}
            source_rows.append(source)
            metadata_only = all(not raw_text(c.value).strip() or c.coordinate in date_cells
                                or DATE_LABEL.search(raw_text(c.value)) for c in cells[1:6])
            if metadata_only or (
                any(re.fullmatch(r"(?:SUB\s*TOTAL|GRAND\s*TOTAL|TOTAL)\s*:?", raw_text(v).strip(), re.I)
                    for v in (title.value, identifier.value))
                and not raw_text(system.value).strip()
            ):
                source["outcome"] = "non_product"
                summary["non_product_rows_skipped"] += 1
                continue
            summary["rows_encountered"] += 1
            systems[raw_text(system.value)] += 1
            if USED.search(raw_text(title.value)) or USED.search(raw_text(system.value)):
                source["outcome"] = "used"
                summary["used_rows_skipped"] += 1
                continue
            try:
                if any(c.data_type == "f" for c in cells[1:6]):
                    raise ValueError("Formula in an imported field; supply literal supplier values")
                if any(not isinstance(c.value, str) or not c.value.strip() for c in (title, system, identifier)):
                    raise ValueError("TITLE, SYS and UPC / SKU must be nonempty text; numeric identifiers cannot be safely reconstructed")
                if any(len(raw_text(v)) > 2000 for v in values):
                    raise ValueError("Source field exceeds 2000 characters")
                meta = identifier_metadata(identifier.value)
                row = {"raw_title": title.value, "raw_system": system.value,
                       "raw_identifier": identifier.value, **meta,
                       "supplier_price": supplier_price(price.value), "currency": "USD",
                       "availability_raw": raw_text(qty.value), **availability(raw_text(qty.value)),
                       "source_row_numbers": [number]}
                row["identity_key"] = product_identity(title.value, system.value, meta["normalized_identifier"])
                source["identity_key"] = row["identity_key"]
                if meta["identifier_status"] != "valid":
                    summary["identifier_warnings"] += 1
                    warnings.append({"row": number, "kind": "identifier", "reason": meta["identifier_status"]})
                if row["availability_min"] is None:
                    summary["availability_warnings"] += 1
                    warnings.append({"row": number, "kind": "availability", "reason": "unknown_quantity"})
                grouped[row["identity_key"]].append((row, source))
                source["outcome"] = "accepted"
            except ValueError as exc:
                source["outcome"] = "invalid"
                summary["invalid_rows_skipped"] += 1
                errors.append({"row": number, "reason": str(exc)})
        products = []
        for key, entries in grouped.items():
            first = entries[0][0]
            compare = lambda row: (row["supplier_price"], row["currency"], row["availability_raw"])
            if any(compare(row) != compare(first) for row, _ in entries[1:]):
                summary["conflict_rows_skipped"] += len(entries)
                errors.append({"identity_key": key, "reason": "Conflicting duplicate product rows",
                               "rows": [row["source_row_numbers"][0] for row, _ in entries]})
                for _, source in entries:
                    source["outcome"] = "conflict"
                continue
            first["source_row_numbers"] = [row["source_row_numbers"][0] for row, _ in entries]
            for _, source in entries[1:]:
                source["outcome"] = "duplicate"
                summary["duplicate_rows_skipped"] += 1
            products.append(first)
        if len(products) > MAX_PRODUCTS:
            raise ValueError("Workbook exceeds 5000 accepted products")
        if summary["rows_encountered"] == 0:
            errors.append({"reason": "No product rows found; refusing an empty current list"})
        summary["rows_imported"] = 0 if errors else len(products)
        summary["products_accepted"] = len(products)
        summary["warnings"] = len(warnings)
        summary["errors"] = len(errors)
        return {"supplier_key": SUPPLIER_KEY, "effective_date": dated.isoformat(),
                "date_source": date_source, "filename": path.name,
                "file_sha256": hashlib.sha256(content).hexdigest(), "parser_version": PARSER_VERSION,
                "currency": "USD", "status": "rejected" if errors else "completed",
                "summary": dict(summary), "system_counts": dict(systems),
                "warnings": warnings, "errors": errors, "source_rows": source_rows, "products": products}
    finally:
        workbook.close()


def _converted_workbook(rows: list[list[object]], source_name: str,
                        price_list_date: date | str | None) -> dict:
    if len(rows) > MAX_ROWS or any(len(row) > 50 for row in rows):
        raise ValueError("Supplier file exceeds bounded parser dimensions")
    workbook = Workbook(write_only=False)
    sheet = workbook.active
    sheet.title = "COMPLETE LIST"
    for row in rows:
        sheet.append(row)
    with NamedTemporaryFile(suffix=".xlsx", delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        workbook.save(temp_path)
        parsed = parse_workbook(temp_path, price_list_date)
    finally:
        workbook.close()
        temp_path.unlink(missing_ok=True)
    parsed["filename"] = source_name
    return parsed


def parse_price_list(path: str | Path, price_list_date: date | str | None = None,
                     filename_reference_date: date | datetime | str | None = None) -> dict:
    """Parse XLSX, legacy XLS, or CSV through the Royal v1 row normalizer."""
    path = Path(path)
    content = path.read_bytes()
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("Supplier file exceeds 10 MiB limit")
    suffix = path.suffix.lower()
    supplied = parse_date(price_list_date) if price_list_date is not None else None
    filename_date = filename_effective_date(path.name, filename_reference_date)
    candidate_date = supplied or filename_date
    if suffix == ".xlsx":
        parsed = parse_workbook(path, candidate_date)
    elif suffix == ".csv":
        text = None
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                pass
        if text is None or "\x00" in text:
            raise ValueError("CSV is not valid bounded text")
        try:
            dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = [row for row in csv.reader(StringIO(text), dialect) if any(cell.strip() for cell in row)]
        parsed = _converted_workbook(rows, path.name, candidate_date)
    elif suffix == ".xls":
        try:
            import xlrd
        except ImportError as exc:
            raise ValueError("Legacy XLS support requires the xlrd package") from exc
        book = xlrd.open_workbook(file_contents=content, on_demand=True)
        try:
            if "COMPLETE LIST" not in book.sheet_names():
                raise ValueError("Required COMPLETE LIST sheet is missing")
            source = book.sheet_by_name("COMPLETE LIST")
            rows = [[source.cell_value(r, c) for c in range(source.ncols)] for r in range(source.nrows)]
            parsed = _converted_workbook(rows, path.name, candidate_date)
        finally:
            book.release_resources()
    else:
        raise ValueError("Royal source must be .xlsx, .xls, or .csv")
    parsed["filename"] = path.name
    parsed["file_sha256"] = hashlib.sha256(content).hexdigest()
    if (filename_date and not supplied and parsed["date_source"] == "operator_parameter"
            and parsed["effective_date"] == filename_date.isoformat()):
        parsed["date_source"] = "supplier_filename"
    return parsed
