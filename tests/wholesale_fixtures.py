"""Small synthetic Royal workbooks generated in test temp directories."""
from pathlib import Path

from openpyxl import Workbook

HEADERS = ["ORDER", "TITLE", "SYS", "UPC / SKU", "PRICE", "QTY", "SUB"]


def royal_workbook(path: Path, products: list[tuple], document_date: str | None = None) -> Path:
    book = Workbook()
    sheet = book.active
    sheet.title = "COMPLETE LIST"
    sheet.append(HEADERS)
    for title, system, identifier, price, quantity in products:
        sheet.append([None, title, system, identifier, price, quantity, "=A2*E2"])
    sheet.append([None] * 7)
    sheet.append([None, None, None, "SUBTOTAL:", None, None, "=SUM(G2:G3)"])
    if document_date:
        book.properties.description = f"Price list date: {document_date}"
    book.save(path)
    book.close()
    return path


GAME_A = ("SW2 Animal Crossing New Horizons", "SW2", "045496906023", 18, "144+")
GAME_B = ("PS5 A different game", "PS5", "7-10425-59752-7", 22, 74)
