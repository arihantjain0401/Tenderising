"""Aggregation endpoints for Discovery summaries and the Ask collage."""

from __future__ import annotations

from fastapi import APIRouter

from tenderising.api.deps import SessionDep
from tenderising.service import aggregates as agg

router = APIRouter(prefix="/api/aggregates", tags=["aggregates"])


@router.get("/status")
def status(session: SessionDep) -> dict:
    return {"buckets": agg.count_by_status(session)}


@router.get("/departments")
def departments(session: SessionDep) -> dict:
    return {"buckets": agg.count_by_department(session)}


@router.get("/categories")
def categories(session: SessionDep) -> dict:
    return {"buckets": agg.count_by_category(session)}


@router.get("/deadlines")
def deadlines(session: SessionDep) -> dict:
    return {"buckets": agg.deadline_histogram(session)}


@router.get("/activity")
def activity(session: SessionDep) -> dict:
    return {"points": agg.activity_timeline(session)}


@router.get("/summary")
def summary(session: SessionDep) -> dict:
    return agg.summary(session)
