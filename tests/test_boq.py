from decimal import Decimal

from tenderising.extract.boq import parse_boq_csv
from tenderising.extract.documents import classify_doc_type, is_document_link

CSV = """Item Number,Item Title,Item Description,Item Quantity,Unit of Measure,Consignee ID,Delivery Period (In number of days)
1,Cement,Cement 50kg bag,10,Bag,DELHI,30
2,Cable,XLPE cable,200,Mtr,MUMBAI,45
"""


def test_parse_boq_csv():
    items = parse_boq_csv(CSV)
    assert len(items) == 2
    assert items[0]["item_no"] == "1"
    assert items[0]["description"] == "Cement 50kg bag"
    assert items[0]["quantity"] == Decimal("10")
    assert items[0]["unit"] == "Bag"
    assert items[0]["consignee"] == "DELHI"
    assert items[0]["unit_price"] is None  # prices are never fabricated (§4.6)
    assert items[0]["confidence"] == 0.95


def test_parse_empty_csv():
    assert parse_boq_csv("Item Number,Item Title\n") == []


def test_classify_doc_type():
    assert classify_doc_type(".../OrderItem/BoqLineItemsDocument/x.csv") == "BOQ"
    assert classify_doc_type(".../OrderItem/BoqDocument/y.pdf") == "BOQ"
    assert classify_doc_type(".../apis/v1/gtc/pdfByDate/?date=20260120") == "GTC"
    assert classify_doc_type(".../bidding/downloadOmppdfile/") == "OMP"
    assert (
        classify_doc_type(".../list-of-categories-where-trials-are-allowed.pdf") == "category_list"
    )
    assert classify_doc_type(".../misc/unknown.pdf") == "document"


def test_is_document_link():
    assert is_document_link("https://mkp.gem.gov.in/.../BoqLineItemsDocument/x.csv") is True
    assert is_document_link("https://mkp.gem.gov.in/.../BoqDocument/y.pdf") is True
    assert is_document_link("https://admin.gem.gov.in/apis/v1/gtc/pdfByDate/?date=20260120") is True
    assert is_document_link("https://example.com/not-a-file") is False
    assert is_document_link("mailto:someone@example.com") is False
