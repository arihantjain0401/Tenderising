from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from tenderising.db.models import Base, Bid, BuyerOrg, ChangeEvent
from tenderising.service.store import CuratedStoreService


def _store():
    eng = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng, expire_on_commit=False)
    return CuratedStoreService(S())


def _base_fields(**overrides):
    fields = {
        "status_raw": "0",
        "status_normalized": "Not Evaluated",
        "status_map_version": "buyer_status_v1",
        "b_status_raw": "1",
        "bid_to_ra": False,
        "office_id": None,
    }
    fields.update(overrides)
    return fields


def test_upsert_creates_then_dedups():
    store = _store()
    fields = _base_fields()
    bid, created, changed = store.upsert_bid(
        bid_number="GEM/2026/B/1",
        b_id="1",
        fields=fields,
        fingerprint="fp",
        fingerprint_algo_version="fp_v1",
        source_url="u",
        raw_ref="r",
    )
    assert created is True
    assert changed == []
    assert bid.first_seen is not None and bid.last_seen is not None

    bid2, created2, changed2 = store.upsert_bid(
        bid_number="GEM/2026/B/1",
        b_id="1",
        fields=fields,
        fingerprint="fp",
        fingerprint_algo_version="fp_v1",
        source_url="u",
        raw_ref="r2",
    )
    assert created2 is False
    assert changed2 == []
    assert store.session.query(Bid).count() == 1


def test_upsert_change_appends_events_not_overwrite():
    store = _store()
    store.upsert_bid(
        bid_number="B",
        b_id="1",
        fields=_base_fields(),
        fingerprint="fp1",
        fingerprint_algo_version="fp_v1",
        source_url="u",
        raw_ref="r",
    )
    bid, created, changed = store.upsert_bid(
        bid_number="B",
        b_id="1",
        fields=_base_fields(status_raw="1", status_normalized="Technical Evaluation"),
        fingerprint="fp2",
        fingerprint_algo_version="fp_v1",
        source_url="u",
        raw_ref="r2",
    )
    assert created is False
    assert "status_raw" in changed and "status_normalized" in changed
    assert store.session.query(Bid).count() == 1
    events = store.session.query(ChangeEvent).all()
    assert any(
        e.field == "status_raw" and e.prior_value == "0" and e.new_value == "1" for e in events
    )


def test_buyer_hierarchy_walk_not_flat():
    store = _store()
    office = store.resolve_buyer("Ministry of A", "Dept of B")
    assert office is not None
    dept = store.session.query(BuyerOrg).filter(BuyerOrg.level == "department").one()
    ministry = store.session.query(BuyerOrg).filter(BuyerOrg.level == "ministry").one()
    assert dept.parent_id == ministry.id
    # NA department is skipped, not fabricated
    office2 = store.resolve_buyer("Ministry of A", "NA")
    assert office2 == ministry.id
