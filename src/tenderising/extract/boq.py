"""BOQ extraction from the GeM BoqLineItemsDocument CSV.

The bid-document PDF embeds link annotations to the BOQ files on mkp.gem.gov.in:
- `.../OrderItem/BoqLineItemsDocument/….csv`  -> machine-readable line items
- `.../OrderItem/BoqDocument/….pdf`           -> the BOQ document

The CSV is the authoritative structured source for bid_line_items (§8.17).
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal, InvalidOperation


def _s(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_boq_csv(text: str) -> list[dict]:
    """Parse the BoqLineItemsDocument CSV into bid_line_items dicts.

    Prices are absent from the BOQ CSV (they live in the financial evaluation),
    so unit_price/total_price stay None — never fabricated (§4.6).
    """
    items: list[dict] = []
    for row in csv.DictReader(io.StringIO(text)):
        items.append(
            {
                "item_no": _s(row.get("Item Number")),
                "description": _s(row.get("Item Description")) or _s(row.get("Item Title")),
                "quantity": _dec(row.get("Item Quantity")),
                "unit": _s(row.get("Unit of Measure")),
                "unit_price": None,
                "total_price": None,
                "consignee": _s(row.get("Consignee ID")),
                "page_number": None,
                "confidence": 0.95,
            }
        )
    return items
