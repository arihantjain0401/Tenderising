"""Workspace CRUD service — per-user saved tenders, views, notes, alerts, pipeline, calendar."""

from __future__ import annotations

from datetime import UTC, datetime

from tenderising.db.models import (
    Alert,
    CalendarEvent,
    Note,
    NoteTag,
    PipelineItem,
    Preference,
    SavedTender,
    SavedView,
    SavedWidget,
    Tag,
)
from tenderising.service.store import CuratedStoreService

PIPELINE_STAGES = ("new", "reviewing", "pursuing", "submitted", "won", "lost")


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    return str(value)


class WorkspaceService:
    def __init__(self, store: CuratedStoreService, user_id: int):
        self.store = store
        self.user_id = user_id
        self.s = store.session

    # -- saved tenders -------------------------------------------------------
    def list_saved_tenders(self) -> list[dict]:
        rows = (
            self.s.query(SavedTender)
            .filter(SavedTender.user_id == self.user_id)
            .order_by(SavedTender.created_at.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "bid_number": r.bid_number,
                "snapshot": r.snapshot,
                "note": r.note,
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ]

    def save_tender(
        self, bid_number: str, note: str | None = None, snapshot: dict | None = None
    ) -> dict:
        row = (
            self.s.query(SavedTender)
            .filter(
                SavedTender.user_id == self.user_id, SavedTender.bid_number == bid_number
            )
            .first()
        )
        if row is None:
            row = SavedTender(user_id=self.user_id, bid_number=bid_number)
            self.s.add(row)
        row.note = note if note is not None else row.note
        if snapshot is not None:
            row.snapshot = snapshot
        self.store.commit()
        return {
            "id": row.id,
            "bid_number": row.bid_number,
            "note": row.note,
            "snapshot": row.snapshot,
        }

    def remove_tender(self, item_id: int) -> bool:
        row = (
            self.s.query(SavedTender)
            .filter(SavedTender.id == item_id, SavedTender.user_id == self.user_id)
            .first()
        )
        if row is None:
            return False
        self.s.delete(row)
        self.store.commit()
        return True

    # -- saved views ---------------------------------------------------------
    def list_saved_views(self) -> list[dict]:
        rows = (
            self.s.query(SavedView)
            .filter(SavedView.user_id == self.user_id)
            .order_by(SavedView.updated_at.desc())
            .all()
        )
        return [{"id": r.id, "name": r.name, "filters": r.filters} for r in rows]

    def save_view(self, name: str, filters: dict | None = None) -> dict:
        row = SavedView(user_id=self.user_id, name=name, filters=filters)
        self.s.add(row)
        self.store.commit()
        return {"id": row.id, "name": row.name, "filters": row.filters}

    def update_view(
        self, item_id: int, name: str | None = None, filters: dict | None = None
    ) -> bool:
        row = (
            self.s.query(SavedView)
            .filter(SavedView.id == item_id, SavedView.user_id == self.user_id)
            .first()
        )
        if row is None:
            return False
        if name is not None:
            row.name = name
        if filters is not None:
            row.filters = filters
        self.store.commit()
        return True

    def remove_view(self, item_id: int) -> bool:
        row = (
            self.s.query(SavedView)
            .filter(SavedView.id == item_id, SavedView.user_id == self.user_id)
            .first()
        )
        if row is None:
            return False
        self.s.delete(row)
        self.store.commit()
        return True

    # -- saved widgets -------------------------------------------------------
    def list_widgets(self) -> list[dict]:
        rows = (
            self.s.query(SavedWidget)
            .filter(SavedWidget.user_id == self.user_id)
            .order_by(SavedWidget.created_at.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "title": r.title,
                "data": r.data,
                "session_id": r.session_id,
                "created_at": _iso(r.created_at),
            }
            for r in rows
        ]

    def save_widget(
        self,
        kind: str,
        data: dict | None = None,
        title: str | None = None,
        session_id: str | None = None,
    ) -> dict:
        row = SavedWidget(
            user_id=self.user_id, kind=kind, data=data, title=title, session_id=session_id
        )
        self.s.add(row)
        self.store.commit()
        return {"id": row.id, "kind": row.kind, "title": row.title, "session_id": row.session_id}

    def remove_widget(self, item_id: int) -> bool:
        row = (
            self.s.query(SavedWidget)
            .filter(SavedWidget.id == item_id, SavedWidget.user_id == self.user_id)
            .first()
        )
        if row is None:
            return False
        self.s.delete(row)
        self.store.commit()
        return True

    # -- tags ----------------------------------------------------------------
    def list_tags(self) -> list[dict]:
        rows = self.s.query(Tag).filter(Tag.user_id == self.user_id).order_by(Tag.name).all()
        return [{"id": r.id, "name": r.name, "color": r.color} for r in rows]

    def _get_or_create_tag(self, name: str, color: str | None = None) -> Tag:
        row = self.s.query(Tag).filter(Tag.user_id == self.user_id, Tag.name == name).first()
        if row is None:
            row = Tag(user_id=self.user_id, name=name, color=color)
            self.s.add(row)
            self.s.flush()
        return row

    # -- notes ---------------------------------------------------------------
    def list_notes(self) -> list[dict]:
        rows = (
            self.s.query(Note)
            .filter(Note.user_id == self.user_id)
            .order_by(Note.updated_at.desc())
            .all()
        )
        out = []
        for r in rows:
            tags = (
                self.s.query(Tag.name)
                .join(NoteTag, NoteTag.tag_id == Tag.id)
                .filter(NoteTag.note_id == r.id)
                .all()
            )
            out.append(
                {
                    "id": r.id,
                    "bid_number": r.bid_number,
                    "title": r.title,
                    "body": r.body,
                    "tags": [t[0] for t in tags],
                    "updated_at": _iso(r.updated_at),
                }
            )
        return out

    def create_note(
        self,
        body: str,
        title: str | None = None,
        bid_number: str | None = None,
        tags: list[str] | None = None,
    ) -> dict:
        row = Note(user_id=self.user_id, body=body, title=title, bid_number=bid_number)
        self.s.add(row)
        self.s.flush()
        for name in tags or []:
            tag = self._get_or_create_tag(name)
            self.s.add(NoteTag(note_id=row.id, tag_id=tag.id))
        self.store.commit()
        return {"id": row.id, "title": row.title, "body": row.body, "bid_number": row.bid_number}

    def update_note(self, item_id: int, body: str | None = None, title: str | None = None) -> bool:
        row = self.s.query(Note).filter(Note.id == item_id, Note.user_id == self.user_id).first()
        if row is None:
            return False
        if body is not None:
            row.body = body
        if title is not None:
            row.title = title
        self.store.commit()
        return True

    def remove_note(self, item_id: int) -> bool:
        row = self.s.query(Note).filter(Note.id == item_id, Note.user_id == self.user_id).first()
        if row is None:
            return False
        self.s.query(NoteTag).filter(NoteTag.note_id == row.id).delete()
        self.s.delete(row)
        self.store.commit()
        return True

    # -- alerts --------------------------------------------------------------
    def list_alerts(self) -> list[dict]:
        rows = (
            self.s.query(Alert)
            .filter(Alert.user_id == self.user_id)
            .order_by(Alert.created_at.desc())
            .all()
        )
        return [
            {
                "id": r.id,
                "name": r.name,
                "filters": r.filters,
                "frequency": r.frequency,
                "enabled": r.enabled,
            }
            for r in rows
        ]

    def create_alert(
        self, name: str, filters: dict | None = None, frequency: str | None = None
    ) -> dict:
        row = Alert(user_id=self.user_id, name=name, filters=filters, frequency=frequency)
        self.s.add(row)
        self.store.commit()
        return {"id": row.id, "name": row.name, "filters": row.filters, "frequency": row.frequency}

    def update_alert(self, item_id: int, **fields) -> bool:
        row = self.s.query(Alert).filter(Alert.id == item_id, Alert.user_id == self.user_id).first()
        if row is None:
            return False
        for key, value in fields.items():
            if value is not None and hasattr(row, key):
                setattr(row, key, value)
        self.store.commit()
        return True

    def remove_alert(self, item_id: int) -> bool:
        row = self.s.query(Alert).filter(Alert.id == item_id, Alert.user_id == self.user_id).first()
        if row is None:
            return False
        self.s.delete(row)
        self.store.commit()
        return True

    # -- pipeline ------------------------------------------------------------
    def list_pipeline(self) -> dict:
        rows = (
            self.s.query(PipelineItem)
            .filter(PipelineItem.user_id == self.user_id)
            .order_by(PipelineItem.position)
            .all()
        )
        board = {stage: [] for stage in PIPELINE_STAGES}
        for r in rows:
            stage = r.stage if r.stage in PIPELINE_STAGES else "new"
            board[stage].append(
                {"id": r.id, "bid_number": r.bid_number, "note": r.note, "position": r.position}
            )
        return {"stages": PIPELINE_STAGES, "board": board}

    def add_pipeline(self, bid_number: str, stage: str = "new", note: str | None = None) -> dict:
        if stage not in PIPELINE_STAGES:
            stage = "new"
        row = (
            self.s.query(PipelineItem)
            .filter(PipelineItem.user_id == self.user_id, PipelineItem.bid_number == bid_number)
            .first()
        )
        if row is None:
            row = PipelineItem(user_id=self.user_id, bid_number=bid_number)
            self.s.add(row)
        row.stage = stage
        if note is not None:
            row.note = note
        self.store.commit()
        return {"id": row.id, "bid_number": row.bid_number, "stage": row.stage, "note": row.note}

    def move_pipeline(self, item_id: int, stage: str) -> bool:
        if stage not in PIPELINE_STAGES:
            return False
        row = (
            self.s.query(PipelineItem)
            .filter(PipelineItem.id == item_id, PipelineItem.user_id == self.user_id)
            .first()
        )
        if row is None:
            return False
        row.stage = stage
        self.store.commit()
        return True

    def remove_pipeline(self, item_id: int) -> bool:
        row = (
            self.s.query(PipelineItem)
            .filter(PipelineItem.id == item_id, PipelineItem.user_id == self.user_id)
            .first()
        )
        if row is None:
            return False
        self.s.delete(row)
        self.store.commit()
        return True

    # -- calendar ------------------------------------------------------------
    def list_events(self) -> list[dict]:
        rows = (
            self.s.query(CalendarEvent)
            .filter(CalendarEvent.user_id == self.user_id)
            .order_by(CalendarEvent.starts_at)
            .all()
        )
        return [
            {
                "id": r.id,
                "title": r.title,
                "description": r.description,
                "event_type": r.event_type,
                "starts_at": _iso(r.starts_at),
                "ends_at": _iso(r.ends_at),
            }
            for r in rows
        ]

    def create_event(
        self,
        title: str,
        starts_at: str | None = None,
        ends_at: str | None = None,
        description: str | None = None,
    ) -> dict:
        row = CalendarEvent(
            user_id=self.user_id,
            title=title,
            starts_at=_parse(starts_at),
            ends_at=_parse(ends_at),
            description=description,
        )
        self.s.add(row)
        self.store.commit()
        return {"id": row.id, "title": row.title}

    def remove_event(self, item_id: int) -> bool:
        row = (
            self.s.query(CalendarEvent)
            .filter(CalendarEvent.id == item_id, CalendarEvent.user_id == self.user_id)
            .first()
        )
        if row is None:
            return False
        self.s.delete(row)
        self.store.commit()
        return True

    # -- preferences ---------------------------------------------------------
    def get_preferences(self) -> dict:
        row = self.s.query(Preference).filter(Preference.user_id == self.user_id).first()
        if row is None:
            return {"timezone": None, "default_view": None, "notification_prefs": None}
        return {
            "timezone": row.timezone,
            "default_view": row.default_view,
            "notification_prefs": row.notification_prefs,
        }

    def update_preferences(
        self, timezone: str | None = None, default_view: str | None = None
    ) -> dict:
        row = self.s.query(Preference).filter(Preference.user_id == self.user_id).first()
        if row is None:
            row = Preference(user_id=self.user_id)
            self.s.add(row)
        if timezone is not None:
            row.timezone = timezone
        if default_view is not None:
            row.default_view = default_view
        self.store.commit()
        return self.get_preferences()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
