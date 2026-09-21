from decimal import Decimal

from tenderising.collector.results import parse_result_view

SAMPLE = """
<table>
 <tr><th>S.No.</th><th>Seller Name</th><th>Offered Item</th><th>Participated On</th><th>MSE/MII Status</th><th>Status</th></tr>
 <tr><td>1</td><td>Alpha Corp</td><td>Make: X</td><td>09-07-2018</td><td>N/A</td><td>Qualified</td></tr>
 <tr><td>2</td><td>Beta Ltd</td><td>Make: Y</td><td>09-07-2018</td><td>N/A</td><td>Disqualified</td></tr>
</table>
<table>
 <tr><th>S.No.</th><th>Seller Name</th><th>Offered Item</th><th>Total Price</th><th>Rank</th></tr>
 <tr><td>1</td><td>Alpha Corp</td><td>Item</td><td>₹ 100000.00</td><td>L1</td><td>--&gt;</td></tr>
 <tr><td>2</td><td>Gamma Co</td><td>Item</td><td>₹ 193750.00</td><td>L2</td><td>--&gt;</td></tr>
</table>
"""


def test_parse_technical_and_financial():
    tech, fin = parse_result_view(SAMPLE)
    assert len(tech) == 2
    assert tech[0]["seller_name"] == "Alpha Corp"
    assert tech[0]["status"] == "Qualified"
    assert tech[1]["status"] == "Disqualified"

    assert len(fin) == 2
    assert fin[0]["rank"] == "L1"
    assert fin[0]["total_price"] == Decimal("100000.00")
    assert fin[1]["rank"] == "L2"


def test_parse_empty_html():
    tech, fin = parse_result_view("<html><body>no tables</body></html>")
    assert tech == [] and fin == []
