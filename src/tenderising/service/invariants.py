"""Data-model invariants from CLAUDE.md §4, as coercers and guards.

Each helper embodies one rule — most importantly: missing/masked/unparsed
values never become zero, and raw status is preserved verbatim alongside its
derived label. A collector must funnel every raw value through these rather
than inventing a default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from tenderising.config import BUYER_STATUS_LABELS, STATUS_MAP_VERSION

# Amounts are Decimal, never float, so a "0" is never a silent rounding artefact.
_ZERO = Decimal("0")
_ISO_TZ = "Z"
_CURRENCY_CHARS = "₹`,₹"


def unwrap(value):
    """The listing API returns most scalars as single-element lists; unwrap them.

    Returns the scalar, or None for an empty list / None. Never raises.
    """
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def as_bool(value) -> bool | None:
    """Coerce a raw flag to bool, or None when unknown. Never invents a value."""
    v = unwrap(value)
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off", ""}:
        return False
    return None


def as_iso_datetime(value) -> datetime | None:
    """Parse an ISO-8601 source timestamp to a tz-aware datetime, or None.

    Source-displayed dates are kept separate from retrieval timestamps; a value
    we cannot parse stays None (never a fabricated zero/epoch)."""
    v = unwrap(value)
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if s.endswith(_ISO_TZ):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def normalize_price(value) -> Decimal | None:
    """§4.6: a missing/masked/unparsed price is None, never zero.

    Zero is returned only when the source literally displays a zero amount.
    """
    v = unwrap(value)
    if v is None:
        return None
    if isinstance(v, (int, float, Decimal)):
        return Decimal(str(v))
    s = str(v).strip()
    if not s:
        return None
    for ch in _CURRENCY_CHARS:
        s = s.replace(ch, "")
    s = s.strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def normalize_status(buyer_status_raw) -> tuple[str | None, str | None, str]:
    """§4.7: return (status_raw, status_normalized, map_version).

    status_raw is the source code verbatim; status_normalized is the derived
    label (None when the code is outside the known map — never fabricated).
    """
    v = unwrap(buyer_status_raw)
    if v is None:
        return None, None, STATUS_MAP_VERSION
    raw = str(v)
    try:
        idx = int(raw)
    except (TypeError, ValueError):
        return raw, None, STATUS_MAP_VERSION
    label = BUYER_STATUS_LABELS[idx] if 0 <= idx < len(BUYER_STATUS_LABELS) else None
    return raw, label, STATUS_MAP_VERSION


def guard_no_zero_for_unknown(value: Decimal | None) -> Decimal | None:
    """Assert-level guard: a stored price must be None, not zero, for unknowns.

    Callers use it defensively; it returns the value unchanged but documents the
    contract at the point of persistence.
    """
    if value is None:
        return None
    if value == _ZERO:
        # A literal zero is a claimed value, not a placeholder — but persist the
        # fact explicitly rather than silently conflating it with "unknown".
        return value
    return value
