from datetime import UTC, datetime, timedelta

from tenderising.api.schemas import _status_label


def test_awarded():
    d = {"status_normalized": "Bid Award", "b_status_raw": "1", "end_date": None}
    assert _status_label(d) == "Awarded"


def test_open():
    end = datetime.now(UTC) + timedelta(days=30)
    d = {"status_normalized": "Not Evaluated", "b_status_raw": "1", "end_date": end}
    assert _status_label(d) == "Open"


def test_closing_soon():
    end = datetime.now(UTC) + timedelta(days=3)
    d = {"status_normalized": None, "b_status_raw": "1", "end_date": end}
    assert _status_label(d) == "Closing soon"


def test_closed():
    d = {"status_normalized": None, "b_status_raw": "2", "end_date": None}
    assert _status_label(d) == "Closed"


def test_status_unavailable():
    d = {"status_normalized": None, "b_status_raw": None, "end_date": None}
    assert _status_label(d) == "Status unavailable"
