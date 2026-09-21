"""PDF extraction (§9): raw text, in-PDF links, and BOQ/price-schedule line items.

Line-item parsing is heuristic; every cell that cannot be parsed stays None
(§4.6 — never fabricated), and each item carries a confidence value.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

import pymupdf

from tenderising.service.invariants import normalize_price

URL_RE = re.compile(r"https?://[^\s)\]\">']+")

_HEADER_ALIASES = {
    "item_no": {"no", "sl", "s.no", "sr", "sr.no", "item no", "sl.no", "s no"},
    "description": {
        "description",
        "item",
        "item description",
        "desc",
        "specification",
        "particulars",
    },
    "quantity": {"qty", "quantity", "qty.", "quantity required", "qty req"},
    "unit": {"unit", "uom", "unit of measure"},
    "unit_price": {"unit price", "rate", "price", "unit rate"},
    "total_price": {"total", "amount", "total price", "total amount", "value"},
    "consignee": {"consignee", "consignee name", "delivery", "destination"},
}


def extract_text(data: bytes) -> str:
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def extract_links(data: bytes) -> list[dict]:
    """URI annotations + regex URLs, each with page number and anchor/context."""
    links: list[dict] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for pno, page in enumerate(doc, start=1):
            for link in page.get_links():
                uri = link.get("uri")
                if uri and uri.startswith("http"):
                    links.append(
                        {"url": uri, "page_number": pno, "anchor_text": None, "context": None}
                    )
            text = page.get_text()
            for m in URL_RE.finditer(text):
                url = m.group(0).rstrip(".,;:)]}")
                s = max(0, m.start() - 60)
                e = min(len(text), m.end() + 60)
                links.append(
                    {
                        "url": url,
                        "page_number": pno,
                        "anchor_text": text[s : m.start()].strip()[-40:] or None,
                        "context": text[s:e].strip(),
                    }
                )
    return links


def _map_columns(header: list[str]) -> dict[str, int] | None:
    colmap: dict[str, int] = {}
    for idx, cell in enumerate(header):
        key = cell.strip().lower()
        for field, aliases in _HEADER_ALIASES.items():
            if key in aliases and field not in colmap:
                colmap[field] = idx
    if "description" in colmap and (
        "unit_price" in colmap or "total_price" in colmap or "quantity" in colmap
    ):
        return colmap
    return None


def _cell(row, idx):
    if idx is None or idx >= len(row):
        return None
    v = row[idx]
    return None if v is None else str(v).strip()


def _to_decimal(s):
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return normalize_price(s)  # handles currency/commas


def extract_line_items(data: bytes) -> list[dict]:
    """Best-effort BOQ/price-schedule line items with per-item confidence."""
    items: list[dict] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for pno, page in enumerate(doc, start=1):
            try:
                tables = page.find_tables()
            except Exception:  # noqa: BLE001
                continue
            for table in tables.tables:
                rows = table.extract()
                if not rows:
                    continue
                colmap = _map_columns([str(c or "").lower() for c in rows[0]])
                if colmap is None:
                    continue
                has_price = "unit_price" in colmap or "total_price" in colmap
                for row in rows[1:]:
                    description = _cell(row, colmap.get("description"))
                    unit_price = _to_decimal(_cell(row, colmap.get("unit_price")))
                    total_price = _to_decimal(_cell(row, colmap.get("total_price")))
                    quantity = _to_decimal(_cell(row, colmap.get("quantity")))
                    if not description and unit_price is None and total_price is None:
                        continue
                    confidence = 0.6 if has_price else 0.4
                    if quantity is not None:
                        confidence += 0.1
                    items.append(
                        {
                            "item_no": _cell(row, colmap.get("item_no")),
                            "description": description,
                            "quantity": quantity,
                            "unit": _cell(row, colmap.get("unit")),
                            "unit_price": unit_price,
                            "total_price": total_price,
                            "consignee": _cell(row, colmap.get("consignee")),
                            "page_number": pno,
                            "confidence": round(min(confidence, 1.0), 2),
                        }
                    )
    return items
