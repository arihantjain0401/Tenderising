"""ORM models. Importing this package registers every table on Base.metadata."""

from tenderising.db.models.auction import Award, Contract, DirectOrder, ReverseAuction
from tenderising.db.models.base import Base, ProvenanceMixin, utcnow
from tenderising.db.models.bids import (
    Bid,
    BidCorrigendum,
    BidDocument,
    BidLineItem,
    DocumentLink,
)
from tenderising.db.models.collection import (
    BidPollState,
    ChangeEvent,
    CollectionRun,
    RawEvidence,
)
from tenderising.db.models.parties import (
    BuyerOrg,
    Category,
    Participation,
    Seller,
    SellerCapacityScope,
)
from tenderising.db.models.workspace import (
    Alert,
    CalendarEvent,
    GoogleIdentity,
    Note,
    NoteTag,
    PipelineItem,
    Preference,
    SavedTender,
    SavedView,
    SavedWidget,
    Session,
    Tag,
    User,
)

__all__ = [
    "Base",
    "ProvenanceMixin",
    "utcnow",
    "Bid",
    "BidCorrigendum",
    "BidDocument",
    "BidLineItem",
    "DocumentLink",
    "ReverseAuction",
    "Award",
    "Contract",
    "DirectOrder",
    "Seller",
    "SellerCapacityScope",
    "BuyerOrg",
    "Category",
    "Participation",
    "CollectionRun",
    "RawEvidence",
    "ChangeEvent",
    "BidPollState",
    "User",
    "GoogleIdentity",
    "Session",
    "SavedTender",
    "SavedView",
    "SavedWidget",
    "Note",
    "Tag",
    "NoteTag",
    "Alert",
    "PipelineItem",
    "CalendarEvent",
    "Preference",
]
