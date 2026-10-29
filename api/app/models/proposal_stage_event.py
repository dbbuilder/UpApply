"""Append-only ledger of proposal stage transitions (migration 027).

A before_flush hook writes one row whenever a proposal is created or its canonical stage
changes, so every write path is covered. Rows are never updated or deleted by the app.
proposal_id has no foreign key on purpose: history outlives a deleted proposal.
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, event, func, inspect
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.database import Base
from app.models.proposal import Proposal
from app.services.proposal_status import UNKNOWN


class ProposalStageEvent(Base):
    __tablename__ = "proposal_stage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    proposal_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_stage: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # None = created
    to_stage: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


@event.listens_for(Session, "before_flush")
def _record_stage_transitions(session: Session, _flush_context, _instances) -> None:
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, Proposal):
            continue
        if obj in session.new:
            from_stage, source = None, obj.__dict__.get("_stage_source") or obj.source or "manual"
        else:
            hist = inspect(obj).attrs.stage.history
            from_stage = hist.deleted[0] if hist.deleted else None
            if not hist.added or hist.added[0] == from_stage:
                continue
            source = obj.__dict__.get("_stage_source") or "api"
        if obj.id is None:
            obj.id = str(uuid4())
        session.add(ProposalStageEvent(
            proposal_id=obj.id, user_id=obj.user_id, from_stage=from_stage,
            to_stage=obj.stage or UNKNOWN, raw_status=obj.status[:50] if obj.status else None,
            source=source[:50],
        ))
        obj.__dict__.pop("_stage_source", None)
