from tenderising.collector.corrigenda import parse_corrigendum_list

SAMPLE = """
<div class="well">
  <span id=span_4067323><strong>Modified On: </strong><span>2026-03-01 15:42:07</span></span>
  <div>Bid extended to <strong>2026-11-28 20:00:00</strong></div>
</div>
<div class="well">
  <span id=span_9999999><strong>Modified On: </strong><span>2026-04-05 10:00:00</span></span>
</div>
<script>$('.view_tc').attr('data-id');</script>
"""


def test_parse_corrigendum_list():
    items = parse_corrigendum_list(SAMPLE)
    assert items == [
        {"iid": "4067323", "modified_on": "2026-03-01 15:42:07"},
        {"iid": "9999999", "modified_on": "2026-04-05 10:00:00"},
    ]


def test_parse_empty():
    assert parse_corrigendum_list("<html>no corrigenda</html>") == []
