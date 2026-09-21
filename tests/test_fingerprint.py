from tenderising.collector.fingerprint import bid_fingerprint


def test_fingerprint_stable():
    fields = {"status_raw": "0", "end_date": "2026-09-20T09:00:00+00:00", "bid_to_ra": False}
    assert bid_fingerprint(fields) == bid_fingerprint(dict(fields))


def test_fingerprint_changes_on_field_change():
    fields = {"status_raw": "0", "bid_to_ra": False}
    assert bid_fingerprint(fields) != bid_fingerprint({**fields, "status_raw": "1"})


def test_fingerprint_key_order_independent():
    a = {"status_raw": "0", "b_status_raw": "1"}
    b = {"b_status_raw": "1", "status_raw": "0"}
    assert bid_fingerprint(a) == bid_fingerprint(b)


def test_fingerprint_includes_document_hashes():
    fields = {"status_raw": "0"}
    base = bid_fingerprint(fields)
    with_docs = bid_fingerprint(fields, document_sha256s=["aaa", "bbb"])
    assert base != with_docs
    # sorted, so order of doc hashes is irrelevant
    assert bid_fingerprint(fields, ["bbb", "aaa"]) == with_docs
