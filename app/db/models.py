import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WorkflowStatus(str, enum.Enum):
    received = "received"
    drafting = "drafting"
    reviewing = "reviewing"
    revise = "revise"
    approved = "approved"
    escalated = "escalated"
    needs_human_approval = "needs_human_approval"
    failed = "failed"


class DecisionType(str, enum.Enum):
    approve = "approve"
    revise = "revise"
    escalate = "escalate"


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    external_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    customer_email: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64), default="unknown")
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.received)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id"), index=True)
    status: Mapped[WorkflowStatus] = mapped_column(Enum(WorkflowStatus), default=WorkflowStatus.drafting)
    iteration_count: Mapped[int] = mapped_column(Integer, default=0)
    final_decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    final_draft_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_action: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    iteration: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(64))
    decision: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    draft_response: Mapped[str] = mapped_column(Text)
    review_notes: Mapped[str] = mapped_column(Text)
    next_action: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReviewMemory(Base):
    __tablename__ = "review_memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tickets.id"), nullable=True)
    memory_text: Mapped[str] = mapped_column(Text)
    reviewer_action: Mapped[str] = mapped_column(String(128))
    embedding_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApprovalAction(Base):
    __tablename__ = "approval_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_run_id: Mapped[int] = mapped_column(ForeignKey("workflow_runs.id"), index=True)
    approver: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(32))
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
