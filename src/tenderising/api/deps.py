"""FastAPI dependencies: DB sessions, service instances, request parsing."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from tenderising.api.auth import sessions as auth_sessions
from tenderising.db.engine import SessionLocal
from tenderising.db.models import User
from tenderising.service.skills import Skills
from tenderising.service.store import CuratedStoreService

COOKIE_NAME = "tenderising_session"


def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_skills(session: Annotated[Session, Depends(get_session)]) -> Skills:
    return Skills(CuratedStoreService(session))


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid date: {value}") from exc


def get_current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE_NAME)
    user_id = auth_sessions.validate(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.id == user_id).first()
    finally:
        session.close()
    if user is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    return user


SessionDep = Annotated[Session, Depends(get_session)]
SkillsDep = Annotated[Skills, Depends(get_skills)]
CurrentUser = Annotated[User, Depends(get_current_user)]
