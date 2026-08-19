"""
SQLAlchemy models for site budgeting (additive tables only — no changes to core CRM tables).
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class FactorMode(str, enum.Enum):
    MULTIPLICATIVE = "MULTIPLICATIVE"
    ADDITIVE = "ADDITIVE"
    # PASS_THROUGH removed: it is an element cost_type (cost_element.cost_type),
    # not a factor application mode. Guide §3.1 vs §3.2.


class BudgetingAuditAction(str, enum.Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class ElementCategory(Base):
    """Hierarchical taxonomy for cost elements (self-referencing)."""
    __tablename__ = "element_category"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("element_category.id", ondelete="SET NULL"), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    parent = relationship("ElementCategory", remote_side="ElementCategory.id", foreign_keys=[parent_id])
    children = relationship("ElementCategory", back_populates="parent", foreign_keys=[parent_id])

    __table_args__ = (
        Index("ix_element_category_parent_id", "parent_id"),
    )


class CostElement(Base):
    __tablename__ = "cost_element"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    unit_of_measure = Column(String(50), nullable=False, default="unit")  # spec: unit_of_measure NOT NULL
    category_id = Column(UUID(as_uuid=True), ForeignKey("element_category.id", ondelete="SET NULL"), nullable=True)
    element_type = Column(String(20), nullable=False, default="ATOMIC")   # ATOMIC | BUNDLE
    cost_type = Column(String(30), nullable=False, default="PER_VISIT")   # PER_VISIT | PER_PATIENT | FIXED | MILESTONE | PASS_THROUGH
    therapeutic_area = Column(String(100), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cost_versions = relationship("ElementCostVersion", back_populates="cost_element", cascade="all, delete-orphan")
    category = relationship("ElementCategory", foreign_keys=[category_id])
    bundle_children = relationship(
        "ElementBundleComposition",
        foreign_keys="ElementBundleComposition.bundle_element_id",
        back_populates="bundle_element",
        cascade="all, delete-orphan",
    )


class ElementBundleComposition(Base):
    """Maps a BUNDLE cost element to its ATOMIC children."""
    __tablename__ = "element_bundle_composition"

    bundle_element_id = Column(UUID(as_uuid=True), ForeignKey("cost_element.id", ondelete="CASCADE"), primary_key=True)
    child_element_id = Column(UUID(as_uuid=True), ForeignKey("cost_element.id", ondelete="CASCADE"), primary_key=True)
    quantity_in_bundle = Column(Numeric(10, 4), nullable=False, default=1)
    sort_order = Column(Integer, nullable=False, default=0)

    bundle_element = relationship("CostElement", foreign_keys=[bundle_element_id], back_populates="bundle_children")
    child_element = relationship("CostElement", foreign_keys=[child_element_id])

    __table_args__ = (
        Index("ix_ebc_bundle_element_id", "bundle_element_id"),
        Index("ix_ebc_child_element_id", "child_element_id"),
    )


class ElementCostVersion(Base):
    __tablename__ = "element_cost_version"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    element_id = Column(UUID(as_uuid=True), ForeignKey("cost_element.id", ondelete="CASCADE"), nullable=False)  # spec: element_id
    version_label = Column(String(100), nullable=False)
    base_unit_cost = Column(Numeric(12, 4), nullable=False)    # spec: base_unit_cost
    reference_currency = Column(String(3), nullable=False, default="USD")  # spec: reference_currency CHAR(3)
    effective_from = Column(Date, nullable=True)
    effective_to = Column(Date, nullable=True)
    source = Column(String(100), nullable=True)
    is_bundle_override = Column(Boolean, nullable=False, default=False)
    created_by = Column(String(255), nullable=True)
    approved_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    cost_element = relationship("CostElement", back_populates="cost_versions")

    __table_args__ = (
        UniqueConstraint("element_id", "version_label", name="uq_element_cost_version_label"),
        Index("ix_element_cost_version_element_id", "element_id"),
    )


class ConversionFactorType(Base):
    __tablename__ = "conversion_factor_type"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    mode = Column(String(32), nullable=False)  # FactorMode values
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    factors = relationship("ConversionFactor", back_populates="factor_type")


class ConversionFactor(Base):
    __tablename__ = "conversion_factor"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    factor_type_id = Column(
        UUID(as_uuid=True), ForeignKey("conversion_factor_type.id", ondelete="RESTRICT"), nullable=False
    )
    trial_id = Column(UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=True)
    country_code = Column(String(3), nullable=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=True)
    sequence_order = Column(Integer, nullable=False, default=0)
    value = Column(Numeric(18, 6), nullable=False)
    currency_code = Column(String(3), nullable=True)
    label = Column(String(255), nullable=True)
    justification = Column(Text, nullable=True)  # guide §3.2: why this value was chosen
    # Scope for resolve_factor() priority (guide §3.3): GLOBAL | ELEMENT | CATEGORY
    scope_level = Column(String(32), nullable=True)
    scope_element_id = Column(UUID(as_uuid=True), ForeignKey("cost_element.id", ondelete="SET NULL"), nullable=True)
    scope_category = Column(String(200), nullable=True)
    # scope_type / scope_value REMOVED: were legacy high-level UI overlay, unused by factor engine.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    factor_type = relationship("ConversionFactorType", back_populates="factors")

    __table_args__ = (
        Index("ix_conversion_factor_trial_id", "trial_id"),
        Index("ix_conversion_factor_site_id", "site_id"),
        Index("ix_conversion_factor_country_code", "country_code"),
    )


class TrialFactorConfiguration(Base):
    """
    Defines which conversion factor TYPES are active for a trial and their application sequence.
    Guide §3.2: PK is (trial_id, factor_type_id), not a reference to a specific factor value.

    Previously this table linked to conversion_factor.id (a specific value) — that was wrong.
    Migrated to link to conversion_factor_type.id (a type) via refactor_trial_factor_configuration.py.
    """
    __tablename__ = "trial_factor_configuration"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trial_id = Column(UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    factor_type_id = Column(
        UUID(as_uuid=True), ForeignKey("conversion_factor_type.id", ondelete="CASCADE"), nullable=False
    )
    application_sequence = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    factor_type = relationship("ConversionFactorType")

    __table_args__ = (
        UniqueConstraint("trial_id", "factor_type_id", name="uq_trial_factor_config_type"),
        Index("ix_trial_factor_configuration_trial_id", "trial_id"),
        Index("ix_trial_factor_config_trial_type", "trial_id", "factor_type_id"),
    )


class CurrencyExchangeRate(Base):
    __tablename__ = "currency_exchange_rate"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_currency = Column(String(3), nullable=False)
    to_currency = Column(String(3), nullable=False)
    rate = Column(Numeric(18, 8), nullable=False)
    effective_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index(
            "ix_currency_exchange_rate_pair_date",
            "from_currency",
            "to_currency",
            "effective_date",
        ),
    )


class TemplateLevel(str, enum.Enum):
    TRIAL = "TRIAL"
    COUNTRY = "COUNTRY"
    SITE = "SITE"


class BudgetTemplate(Base):
    __tablename__ = "budget_template"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trial_id = Column(UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    # Legacy: site-level templates; for true cascade use template_level + parent_template_id.
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="SET NULL"), nullable=True)
    parent_template_id = Column(UUID(as_uuid=True), ForeignKey("budget_template.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(500), nullable=False)
    status = Column(String(50), nullable=False, default="draft")
    enrollment_planned = Column(Integer, nullable=True)
    target_currency_code = Column(String(3), nullable=False, default="USD")
    # Cascade metadata: TRIAL / COUNTRY / SITE + optional country_code.
    template_level = Column(String(32), nullable=True)
    country_code = Column(String(3), nullable=True)
    # Locked FMV vintage for finalized templates; compute_final_unit_cost uses this when set (or when status is executed/approved).
    cost_version_label = Column(String(100), nullable=True)
    # Snapshotted on APPROVED→EXECUTED transition (guide §3.4, design decision #6)
    locked_exchange_rate_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    parent_template = relationship(
        "BudgetTemplate",
        remote_side="BudgetTemplate.id",
        foreign_keys=[parent_template_id],
    )
    line_items = relationship(
        "BudgetLineItem",
        back_populates="template",
        foreign_keys="BudgetLineItem.budget_template_id",
    )
    visit_schedules = relationship("VisitSchedule", back_populates="template")
    milestones = relationship("BudgetMilestone", back_populates="template")
    notes = relationship("BudgetNote", back_populates="template")
    personnel_roles = relationship("BudgetPersonnelRole", back_populates="template")

    __table_args__ = (
        Index("ix_budget_template_trial_id", "trial_id"),
        Index("ix_budget_template_site_id", "site_id"),
        Index("ix_budget_template_trial_level", "trial_id", "template_level"),
        Index("ix_budget_template_trial_country", "trial_id", "country_code"),
    )


class BudgetLineItem(Base):
    __tablename__ = "budget_line_item"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_template_id = Column(UUID(as_uuid=True), ForeignKey("budget_template.id", ondelete="CASCADE"), nullable=False)
    cost_element_id = Column(UUID(as_uuid=True), ForeignKey("cost_element.id", ondelete="RESTRICT"), nullable=False)
    # is_excluded: single flag replacing the old (included, excluded) dual-boolean pair.
    # included/excluded REMOVED — dual booleans created ambiguous 4-state logic (guide §3.4).
    is_excluded = Column(Boolean, nullable=False, default=False)
    override_unit_cost = Column(Numeric(18, 4), nullable=True)
    override_currency_code = Column(String(3), nullable=True)
    inherited_from_parent = Column(Boolean, nullable=False, default=False)
    override_quantity = Column(Numeric(18, 4), nullable=True)
    default_quantity = Column(Numeric(10, 2), nullable=True)  # trial-level default qty (guide §3.4)
    needs_review = Column(Boolean, nullable=False, default=False)
    # parent_line_item_id REMOVED: shadow cascade hierarchy conflicted with template-level cascade.
    sort_order = Column(Integer, nullable=False, default=0)
    # SOA section title at the time of import (e.g. "ELIGIBILITY", "ASSESSMENTS").
    # Used by the matrix UI to group rows under their SOA section header. Stored
    # per-line-item so reused catalog elements (Physical Exam etc) still carry the
    # SOA's section instead of the catalog's global category.
    soa_section = Column(String(255), nullable=True)
    # Policy-refactor flag: set True at COUNTRY level when a country policy doc
    # explicitly lists this element as IN-SCOPE / required for the budget. Pairs
    # with is_excluded (which is set True for policy-driven exclusions). Both flags
    # let the UI visually distinguish policy-driven rows (green=included, red=excluded).
    is_policy_included = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    template = relationship("BudgetTemplate", back_populates="line_items", foreign_keys=[budget_template_id])
    cost_element = relationship("CostElement")
    visit_matrix_entries = relationship("BudgetVisitMatrix", back_populates="line_item")

    __table_args__ = (
        Index("ix_budget_line_item_template_id", "budget_template_id"),
        Index("ix_budget_line_item_cost_element_id", "cost_element_id"),
    )


class VisitSchedule(Base):
    """
    Trial-level canonical visit schedule (guide §3.5).

    Refactored from per-template to per-trial (refactor_visit_schedule_trial_scoped migration).
    budget_template_id is kept for backward compatibility with existing matrix FK references
    until the full cutover is verified; new code should use trial_id.

    WidgetScheduleVisit is DEPRECATED in favour of this table (see drop_widget_schedule_visit migration).
    """
    __tablename__ = "visit_schedule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Primary scope: trial (guide §3.5)
    trial_id = Column(UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=True)
    # Kept for backward compat — points to the template that originally created this row.
    # Null for rows migrated from widget_schedule_visit.
    budget_template_id = Column(UUID(as_uuid=True), ForeignKey("budget_template.id", ondelete="SET NULL"), nullable=True)
    visit_code = Column(String(100), nullable=True)
    visit_name = Column(String(255), nullable=False)
    # New classification (replaces unused legacy enum SCREENING/TREATMENT/etc):
    #   fixed       — single-occurrence visits (Screening, Baseline, EOT, Safety FU)
    #   frequency   — recurring visits with interval/window metadata
    #   unscheduled — UNS1, UNS2 …
    visit_type = Column(String(20), nullable=True)
    interval_weeks = Column(Integer, nullable=True)   # for frequency visits
    start_week = Column(Integer, nullable=True)       # for treatment-bounded frequency (e.g. q8w from wk 13)
    end_week = Column(Integer, nullable=True)         # for treatment-bounded frequency (e.g. q8w thru wk 49)
    target_day = Column(Integer, nullable=True)       # Protocol day number (e.g. -14, 1, 29)
    window_before = Column(Integer, nullable=True)    # Days before target (visit window) — guide §3.5
    window_after = Column(Integer, nullable=True)     # Days after target
    visit_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    country_code = Column(String(3), nullable=True)   # NULL = all countries; non-null = country-specific visit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    template = relationship("BudgetTemplate", back_populates="visit_schedules", foreign_keys=[budget_template_id])
    matrix_entries = relationship("BudgetVisitMatrix", back_populates="visit_schedule")

    __table_args__ = (
        Index("ix_visit_schedule_trial_id", "trial_id"),
        Index("ix_visit_schedule_budget_template_id", "budget_template_id"),
    )


class BudgetVisitMatrix(Base):
    __tablename__ = "budget_visit_matrix"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_line_item_id = Column(UUID(as_uuid=True), ForeignKey("budget_line_item.id", ondelete="CASCADE"), nullable=False)
    visit_schedule_id = Column(UUID(as_uuid=True), ForeignKey("visit_schedule.id", ondelete="CASCADE"), nullable=False)
    units = Column(Numeric(18, 4), nullable=False, default=1)
    is_excluded = Column(Boolean, nullable=False, default=False)

    line_item = relationship("BudgetLineItem", back_populates="visit_matrix_entries")
    visit_schedule = relationship("VisitSchedule", back_populates="matrix_entries")

    __table_args__ = (
        UniqueConstraint("budget_line_item_id", "visit_schedule_id", name="uq_budget_visit_matrix_line_visit"),
    )


class BudgetMilestone(Base):
    __tablename__ = "budget_milestone"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_template_id = Column(UUID(as_uuid=True), ForeignKey("budget_template.id", ondelete="CASCADE"), nullable=False)
    # element_id: NULLABLE FK to cost_element for library-backed milestones (guide §3.6)
    element_id = Column(UUID(as_uuid=True), ForeignKey("cost_element.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(500), nullable=False)
    # unit_cost: renamed from 'amount' to match guide §3.6 naming
    unit_cost = Column(Numeric(18, 4), nullable=False)
    quantity = Column(Numeric(10, 2), nullable=False, default=1)   # e.g. 2 for "IRB renewal × 2 years"
    payment_trigger = Column(String(200), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    # LLM-populated: NULL = universal (applies to every country/site); "BRA" etc = country-specific
    country_code = Column(String(3), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    template = relationship("BudgetTemplate", back_populates="milestones")
    cost_element = relationship("CostElement", foreign_keys=[element_id])

    __table_args__ = (
        Index("ix_budget_milestone_budget_template_id", "budget_template_id"),
        Index("ix_budget_milestone_country_code", "country_code"),
    )


class BudgetNote(Base):
    __tablename__ = "budget_note"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_template_id = Column(UUID(as_uuid=True), ForeignKey("budget_template.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(255), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    category = Column(String(50), nullable=True)  # e.g. "Payment Terms", "Enrollment Cap", "Pass-Through"
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    template = relationship("BudgetTemplate", back_populates="notes")


class SiteEnrollmentPlan(Base):
    """
    Per-site enrollment plan for the Planned Enrollment tab. Each row maps a
    site under a study to a country-budget (`country_code`), a planned patient
    count, and an activation date. The Rollup Budget tab cascades from these
    rows: variable cost × patients + fixed cost × patients.

    The country_code does NOT have to match the site's facility country —
    users explicitly pick which country budget applies. UNIQUE on (site_id,
    study_id) so each site has at most one plan per study.
    """
    __tablename__ = "site_enrollment_plan"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False)
    country_code = Column(String(8), nullable=True)  # picked from country-budget dropdown
    planned_patients = Column(Integer, nullable=False, default=0)
    planned_activation_date = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("study_id", "site_id", name="uq_site_enrollment_plan_study_site"),
        Index("ix_site_enrollment_plan_study_id", "study_id"),
        Index("ix_site_enrollment_plan_site_id", "site_id"),
    )


class WidgetScheduleVisit(Base):
    """
    DEPRECATED — superseded by VisitSchedule (now trial-scoped).

    After running refactor_visit_schedule_trial_scoped.py, VisitSchedule serves as
    the trial-level canonical visit table. WidgetScheduleVisit data has been migrated
    into VisitSchedule. Run drop_widget_schedule_visit.py migration to remove this table.

    Kept here temporarily to avoid breaking imports during transition period.
    """
    __tablename__ = "widget_schedule_visit"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trial_id = Column(UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    visit_code = Column(String(100), nullable=True)
    visit_name = Column(String(255), nullable=False)
    visit_type = Column(String(50), nullable=True)  # SCREENING | TREATMENT | END_OF_TREATMENT | FOLLOW_UP | UNSCHEDULED
    target_day = Column(Integer, nullable=True)      # Protocol day number e.g. -14, 1, 29
    visit_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_widget_schedule_visit_trial_id", "trial_id"),
    )


class MilestoneLibraryItem(Base):
    """
    Global library of standard clinical trial milestones.
    Users pick from here when adding milestones to a budget template,
    or create milestones manually.
    """
    __tablename__ = "milestone_library_item"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(500), nullable=False)
    default_amount = Column(Numeric(18, 4), nullable=True)   # NULL = user must enter amount
    payment_trigger = Column(String(200), nullable=True)
    category = Column(String(100), nullable=True)            # e.g. Startup, Regulatory, Enrollment, Closeout
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_milestone_library_item_category", "category"),
    )


class BudgetPersonnelRole(Base):
    """
    Personnel effort & cost rows attached to a budget template.

    Formula:
      total_hours  = startup_hrs + screening_hrs + (on_study_hrs_per_month × months) + closeout_hrs
      total_cost   = total_hours × hourly_rate
      oh_amount    = total_cost × (overhead_pct / 100)
      total_incl_oh = total_cost + oh_amount
    """
    __tablename__ = "budget_personnel_role"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    budget_template_id = Column(
        UUID(as_uuid=True), ForeignKey("budget_template.id", ondelete="CASCADE"), nullable=False
    )
    role_name = Column(String(200), nullable=False)
    person_name = Column(String(200), nullable=True)
    hourly_rate = Column(Numeric(10, 2), nullable=False, default=0)
    startup_hrs = Column(Numeric(10, 2), nullable=False, default=0)
    screening_hrs = Column(Numeric(10, 2), nullable=False, default=0)
    on_study_hrs_per_month = Column(Numeric(10, 2), nullable=False, default=0)
    months = Column(Numeric(10, 2), nullable=False, default=0)
    closeout_hrs = Column(Numeric(10, 2), nullable=False, default=0)
    overhead_pct = Column(Numeric(6, 2), nullable=False, default=25)  # % e.g. 25 = 25%
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    template = relationship("BudgetTemplate", back_populates="personnel_roles")

    __table_args__ = (
        Index("ix_budget_personnel_role_template_id", "budget_template_id"),
    )


class SiteBudgetingAuditLog(Base):
    """
    Auditing for site budgeting entities (separate from legacy audit_logs).
    Physical table: site_budgeting_audit_log
    """

    __tablename__ = "site_budgeting_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(String(20), nullable=False)
    cascade_level = Column(String(32), nullable=True)  # TRIAL | COUNTRY | SITE | SYSTEM
    field_name = Column(String(100), nullable=True)     # specific field changed (for UPDATE rows)
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    justification = Column(Text, nullable=True)
    session_id = Column(UUID(as_uuid=True), nullable=True)  # groups related changes in one user action
    user_id = Column(String(255), ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    user_role = Column(String(50), nullable=True)  # role at time of action (guide §3.8)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_site_budgeting_audit_entity", "entity_type", "entity_id"),
        Index("ix_site_budgeting_audit_user_id", "user_id"),
        Index("ix_site_budgeting_audit_session_id", "session_id"),
    )


class BudgetPolicyDocument(Base):
    """
    Country-tagged regulatory / policy document uploaded by the user. Multiple docs per
    (trial_id, country_code) allowed — the LLM concatenates them when extracting
    country-specific milestones.
    """
    __tablename__ = "budget_policy_document"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trial_id = Column(UUID(as_uuid=True), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False)
    country_code = Column(String(3), nullable=False)
    file_name = Column(String(500), nullable=False)
    mime_type = Column(String(120), nullable=False)
    file_size = Column(Integer, nullable=False)
    document_data = Column(LargeBinary, nullable=False)
    uploaded_by = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_budget_policy_document_trial_country", "trial_id", "country_code"),
    )
