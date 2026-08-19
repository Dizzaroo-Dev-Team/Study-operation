"""
models.py
=========

Persistence layer. Four tables capture the whole platform:

  workflow_definitions          one row per document type (CTA, CDA, NDA...)
  workflow_definition_versions  immutable snapshots of the flow JSON
  workflow_instances            one running document walking a definition
  workflow_audit_entries        every action ever taken (GCP-friendly trail)

VERSIONING matters: a running instance points at a specific *version*. Editing a
workflow in the builder creates a NEW version, so in-flight agreements keep
following the exact flow they started on. Nothing already in progress breaks.

CRM integration notes
----------------------
  * Inherits from the shared ``app.db`` Base so these tables register on the same
    metadata as every other model (Alembic / create_all visibility).
  * ``eager_defaults=True`` makes SQLAlchemy fetch server-default columns
    (created_at / updated_at) via RETURNING on INSERT, so the values are present
    immediately after ``flush()`` — the service never calls ``refresh()`` and the
    router can serialize the row straight after the transaction commits.
  * Integer primary keys are intentional: the engine/schemas/router all type
    instance and version ids as ``int``. Kept as-is so the pure layers are
    untouched.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    versions: Mapped[list["WorkflowDefinitionVersion"]] = relationship(
        back_populates="definition",
        cascade="all, delete-orphan",
        order_by="WorkflowDefinitionVersion.version",
    )

    @property
    def latest_version(self) -> int:
        return max((v.version for v in self.versions), default=0)

    @property
    def published_version(self):
        published = [v.version for v in self.versions if v.is_published]
        return max(published) if published else None


class WorkflowDefinitionVersion(Base):
    __tablename__ = "workflow_definition_versions"
    __table_args__ = (UniqueConstraint("definition_id", "version"),)
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    # The full WorkflowDefinitionBody, stored as JSON. This is the flow-as-data.
    body: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    definition: Mapped["WorkflowDefinition"] = relationship(back_populates="versions")


class WorkflowInstance(Base):
    __tablename__ = "workflow_instances"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definition_versions.id"), index=True
    )
    definition_key: Mapped[str] = mapped_column(String(64), index=True)
    definition_version: Mapped[int] = mapped_column(Integer)

    # active | completed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Link back to your domain object (e.g. the agreement id). Opaque to the engine.
    subject_ref: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # V2 Phase 5 — sub-workflow linkage: set when this instance was spawned by a
    # parent's CALL step. Child completion injects ChildCompleted at
    # (parent_instance_id, parent_step_id).
    parent_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    parent_step_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Accumulated variables: form data + flags that conditions read.
    context: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    version: Mapped["WorkflowDefinitionVersion"] = relationship()
    audit_entries: Mapped[list["WorkflowAuditEntry"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="WorkflowAuditEntry.created_at",
    )


class WorkflowTask(Base):
    """V2 Phase 3: a WORK ITEM — distinct from the control-flow step it came
    from. Created when a token parks on a human step (one per open parallel
    branch / current signer slot / parked decision), completed when the matching
    action fires, cancelled when the flow moves past it (quorum met, rework,
    terminal). This table IS the worklist read-model."""

    __tablename__ = "workflow_tasks"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str] = mapped_column(String(128))
    # The slot within the step ('' for whole-step tasks; a branch id for a
    # parallel branch; a signer id for an ordered-signing slot).
    slot_id: Mapped[str] = mapped_column(String(128), default="")
    name: Mapped[str] = mapped_column(String(255))

    # Participant resolution, captured AT CREATION (the policy moment).
    assignee_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    assignee_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # open -> claimed -> completed | cancelled | expired (expiry arrives with timers)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    claimed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    instance: Mapped["WorkflowInstance"] = relationship()


class WorkflowTimer(Base):
    """V2 Phase 4: a durable boundary timer. Armed (by kernel command) when a
    token parks on a step whose config carries {"timer": {seconds, action}};
    the scheduler (Celery / run_due_timers) injects a TimerFired event when
    fire_at passes. The kernel never reads a clock — fire_at is computed at the
    arming boundary."""

    __tablename__ = "workflow_timers"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))   # transition action to fire
    fire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # pending -> fired | cancelled
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    instance: Mapped["WorkflowInstance"] = relationship()


class WorkflowJob(Base):
    """V2 Phase 4: an automated-step execution. Created (kernel command) when a
    token parks on a JOB step; the executor runs the registered handler and
    injects JobCompleted / JobFailed back through the kernel. Retries up to
    max_attempts before taking the job_failed transition. This is the seam for
    real notifications and AI-agent steps."""

    __tablename__ = "workflow_jobs"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(64))      # registry key
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    # pending -> running -> completed | failed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    instance: Mapped["WorkflowInstance"] = relationship()


class WorkflowAuditEntry(Base):
    __tablename__ = "workflow_audit_entries"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), index=True
    )
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    transition_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    from_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    to_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    instance: Mapped["WorkflowInstance"] = relationship(back_populates="audit_entries")
