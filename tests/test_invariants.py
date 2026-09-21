from datetime import UTC

from tenderising.service.invariants import (
    as_bool,
    as_iso_datetime,
    normalize_price,
    normalize_status,
    unwrap,
)


def test_unwrap_list_scalar_none():
    assert unwrap([123]) == 123
    assert unwrap(["x"]) == "x"
    assert unwrap([]) is None
    assert unwrap(None) is None
    assert unwrap("plain") == "plain"


def test_as_bool():
    assert as_bool([1]) is True
    assert as_bool("0") is False
    assert as_bool([True]) is True
    assert as_bool(None) is None
    assert as_bool(["garbage"]) is None


def test_iso_datetime():
    dt = as_iso_datetime(["2026-09-01T10:00:00Z"])
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0
    assert as_iso_datetime(None) is None
    assert as_iso_datetime(["not a date"]) is None


def test_normalize_price_never_zero_for_unknown():
    # §4.6: missing/masked/unparsed -> None, never 0.
    assert normalize_price(None) is None
    assert normalize_price([]) is None
    assert normalize_price([""]) is None
    assert normalize_price("masked") is None
    assert normalize_price(["₹1,00,000.00"]) == 100000
    assert normalize_price([0]) == 0  # a literal zero is a claimed value


def test_normalize_status_raw_preserved():
    raw, normalized, version = normalize_status([3])
    assert raw == "3"
    assert normalized == "Bid Award"
    assert version == "buyer_status_v1"
    # unknown code -> raw preserved, no fabricated label
    raw2, norm2, _ = normalize_status([99])
    assert raw2 == "99"
    assert norm2 is None


def test_timezone_aware():
    dt = as_iso_datetime(["2026-09-01T10:00:00Z"])
    assert dt.tzinfo is UTC
