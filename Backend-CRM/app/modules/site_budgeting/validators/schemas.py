from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── Element Category ────────────────────────────────────────────────────────

class ElementCategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    parent_id: Optional[UUID] = None
    sort_order: int = 0


class ElementCategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    parent_id: Optional[UUID] = None
    sort_order: Optional[int] = None


# ── Cost Element CRUD ────────────────────────────────────────────────────────

class CostElementCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    unit: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = Field(default=None, max_length=200)
    category_id: Optional[UUID] = None
    element_type: Optional[str] = Field(default="ATOMIC", max_length=20)
    cost_type: Optional[str] = Field(default=None, max_length=30)
    therapeutic_area: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = True


class CostElementUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=500)
    description: Optional[str] = None
    unit: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = Field(default=None, max_length=200)
    category_id: Optional[UUID] = None
    element_type: Optional[str] = Field(default=None, max_length=20)
    cost_type: Optional[str] = Field(default=None, max_length=30)
    therapeutic_area: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None


# ── Bundle Composition ───────────────────────────────────────────────────────

class BundleChildUpsert(BaseModel):
    child_element_id: UUID
    quantity_in_bundle: Decimal = Decimal("1")
    sort_order: int = 0


# ── Cost Version ─────────────────────────────────────────────────────────────

class ElementCostUpdate(BaseModel):
    version_label: str = Field(..., min_length=1, max_length=100)
    base_unit_cost: Decimal
    reference_currency: str = Field(default="USD", max_length=3)
    source: Optional[str] = Field(default=None, max_length=100)
    is_bundle_override: bool = False


class ConversionFactorCreate(BaseModel):
    factor_type_id: UUID
    trial_id: Optional[UUID] = None
    country_code: Optional[str] = Field(default=None, max_length=3)
    site_id: Optional[UUID] = None
    sequence_order: int = 0
    value: Decimal
    currency_code: Optional[str] = Field(default=None, max_length=3)
    label: Optional[str] = None
    justification: Optional[str] = None                                  # guide §3.2
    register_for_trial: bool = True
    # scope_type / scope_value REMOVED (legacy, A2) — use scope_level + scope_element_id/scope_category.
    scope_level: Optional[str] = Field(default=None, max_length=32)      # GLOBAL | ELEMENT | CATEGORY
    scope_element_id: Optional[UUID] = None
    scope_category: Optional[str] = Field(default=None, max_length=200)


class BudgetTemplateCreate(BaseModel):
    trial_id: UUID
    site_id: Optional[UUID] = None
    parent_template_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=500)
    enrollment_planned: Optional[int] = None
    target_currency_code: str = Field(default="USD", max_length=3)
    template_level: Optional[str] = Field(default=None, max_length=32)  # TRIAL | COUNTRY | SITE


class BudgetTemplateStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)  # draft, under_review, approved, executed, amended, archived


class BudgetLineItemCreate(BaseModel):
    cost_element_id: UUID
    sort_order: int = 0
    # included/excluded replaced by single is_excluded flag (A3)


class BudgetLineItemUpdate(BaseModel):
    # included/excluded REMOVED (A3) — use is_excluded only (guide §3.4)
    is_excluded: Optional[bool] = None
    override_unit_cost: Optional[Decimal] = None
    override_currency_code: Optional[str] = Field(default=None, max_length=3)
    override_quantity: Optional[Decimal] = None
    needs_review: Optional[bool] = None
    sort_order: Optional[int] = None


class VisitMatrixCell(BaseModel):
    budget_line_item_id: UUID
    visit_schedule_id: UUID
    units: Decimal = Field(default=Decimal("1"))
    is_excluded: Optional[bool] = None


class AmendmentMarkBody(BaseModel):
    element_ids: list[UUID] = Field(default_factory=list)


class VisitMatrixPatch(BaseModel):
    cells: list[VisitMatrixCell]


class VisitScheduleCreate(BaseModel):
    visit_name: str = Field(..., min_length=1, max_length=255)
    visit_code: Optional[str] = Field(default=None, max_length=100)
    visit_order: int = 0
    visit_type: Optional[str] = Field(default=None, max_length=50)   # SCREENING | TREATMENT | END_OF_TREATMENT | FOLLOW_UP | UNSCHEDULED
    target_day: Optional[int] = None


class BudgetMilestoneCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    unit_cost: Decimal                                    # renamed from amount (A6, guide §3.6)
    quantity: Decimal = Decimal("1")
    sort_order: int = 0
    payment_trigger: Optional[str] = Field(default=None, max_length=200)
    element_id: Optional[UUID] = None                    # NULLABLE link to cost_element (guide §3.6)


class BudgetMilestoneUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=500)
    unit_cost: Optional[Decimal] = None                  # renamed from amount (A6)
    quantity: Optional[Decimal] = None
    sort_order: Optional[int] = None
    payment_trigger: Optional[str] = Field(default=None, max_length=200)


class BudgetNoteCreate(BaseModel):
    body: str = Field(..., min_length=1)
    category: Optional[str] = Field(default=None, max_length=50)


class CostElementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: Optional[str] = None
    unit: Optional[str] = None
    category: Optional[str] = None


# ── Widget Schedule ──────────────────────────────────────────────────────────

class WidgetVisitCreate(BaseModel):
    visit_name: str = Field(..., min_length=1, max_length=255)
    visit_code: Optional[str] = Field(default=None, max_length=100)
    visit_order: int = 0
    visit_type: Optional[str] = Field(default=None, max_length=50)
    target_day: Optional[int] = None


class WidgetVisitUpdate(BaseModel):
    visit_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    visit_code: Optional[str] = None
    visit_order: Optional[int] = None
    visit_type: Optional[str] = None
    target_day: Optional[int] = None
    is_active: Optional[bool] = None


class WidgetVisitReorderItem(BaseModel):
    id: UUID
    visit_order: int


class WidgetVisitReorderBody(BaseModel):
    items: list[WidgetVisitReorderItem]


# ── Milestone Library ────────────────────────────────────────────────────────

class MilestoneLibraryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    default_amount: Optional[Decimal] = None
    payment_trigger: Optional[str] = Field(default=None, max_length=200)
    category: Optional[str] = Field(default=None, max_length=100)
    sort_order: int = 0


class MilestoneLibraryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=500)
    default_amount: Optional[Decimal] = None
    payment_trigger: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class MilestoneFromLibraryBody(BaseModel):
    library_item_id: UUID
    quantity: Optional[Decimal] = Decimal("1")
    amount_override: Optional[Decimal] = None


class BudgetTotalsOut(BaseModel):
    template_id: str
    trial_id: str
    target_currency: str
    enrollment_planned: Optional[int] = None
    per_patient_total: str
    milestone_total: str
    total_budget: str
    lines: list[dict[str, Any]]
