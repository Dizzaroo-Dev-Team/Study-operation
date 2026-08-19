from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import IRB, IRBAdministrativeInfo


router = APIRouter()


from pydantic import BaseModel, Field, EmailStr


IRB_TYPES_ALLOWED = frozenset({"Central", "Institutional", "Independent"})

_LEGACY_IRB_TYPE_MAP = {
    "Local / Institutional": "Institutional",
    "Commercial / Independent": "Independent",
    "Government / Regulatory": "Institutional",
}


def _normalize_irb_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s in IRB_TYPES_ALLOWED:
        return s
    return _LEGACY_IRB_TYPE_MAP.get(s)


IEC_TYPES_ALLOWED = frozenset({"Institutional", "Independent"})

_LEGACY_IEC_TYPE_MAP = {
    "Local / Institutional": "Institutional",
    "Commercial / Independent": "Independent",
}


def _normalize_iec_type(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s in IEC_TYPES_ALLOWED:
        return s
    return _LEGACY_IEC_TYPE_MAP.get(s)


class IRBAdministrativeInfoCreate(BaseModel):
    irb_id: Optional[int] = Field(
        default=None,
        description="When set, updates that IRB's admin info; otherwise IRB is resolved by name or created.",
    )

    # Basic Demographics
    organization_type: str = Field(..., min_length=1)
    irb_name: Optional[str] = None
    iec_name: Optional[str] = None
    irb_type: Optional[str] = None
    iec_type: Optional[str] = None
    registration_id: Optional[str] = None
    fwa_number: Optional[str] = None
    ohrp_number: Optional[str] = None
    accreditation_body: Optional[str] = None
    accreditation_number: Optional[str] = None
    accreditation_expiry: Optional[date] = None
    irb_status: Optional[str] = None
    date_established: Optional[date] = None
    jurisdiction: Optional[str] = None

    # Address
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    office_hours: Optional[str] = None
    time_zone: Optional[str] = None

    # Contact - Primary
    primary_contact_name: Optional[str] = None
    primary_contact_job_title: Optional[str] = None
    primary_contact_email: Optional[EmailStr] = None
    primary_contact_phone: Optional[str] = None

    # Contact - Secondary
    secondary_contact_name: Optional[str] = None
    secondary_contact_job_title: Optional[str] = None
    secondary_contact_email: Optional[EmailStr] = None
    secondary_contact_phone: Optional[str] = None

    # Membership
    chair_name: Optional[str] = None
    vice_chair_name: Optional[str] = None
    number_of_members: Optional[int] = Field(default=None, ge=0)
    number_of_alternates: Optional[int] = Field(default=None, ge=0)

    quorum_required: Optional[bool] = None
    quorum_threshold_percent: Optional[float] = None
    quorum_minimum_members_present: Optional[int] = None

    full_board_meeting_frequency: Optional[str] = None
    usual_meeting_day: Optional[str] = None
    meeting_date: Optional[date] = None
    submission_deadline_before_meeting: Optional[str] = None

    submission_type: Optional[str] = None
    submission_date: Optional[date] = None

    submission_method: Optional[str] = None
    number_of_copies_required: Optional[int] = Field(default=None, ge=1)
    submission_fee_currency: Optional[str] = None
    submission_fee_amount: Optional[float] = Field(default=None, ge=0)
    payment_method: Optional[str] = None

    review_catalog: Optional[str] = None
    quality_met: Optional[str] = None
    irb_meeting_review_date: Optional[date] = None

    decision_outcome: Optional[str] = None
    decision_date: Optional[date] = None
    decision_letter_reference: Optional[str] = None
    approval_date: Optional[date] = None

    bank_name: Optional[str] = None
    bank_account_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    routing_swift_code: Optional[str] = None
    iban: Optional[str] = None
    banking_currency: Optional[str] = None
    invoice_address_alt: Optional[str] = None


MEETING_FREQUENCY_ALLOWED = frozenset(
    {"Weekly", "Bi-weekly", "Monthly", "Quarterly", "As needed"}
)

SUBMISSION_TYPES_ALLOWED = frozenset({"Initial", "Amendment"})

SUBMISSION_METHODS_ALLOWED = frozenset(
    {"Online – Portal", "Email", "Hard Copy (Paper)", "Regulatory System"}
)
SUBMISSION_FEE_CURRENCIES_ALLOWED = frozenset({"USD", "INR", "EUR"})
PAYMENT_METHODS_ALLOWED = frozenset(
    {"Credit/Debit Card", "Bank/Wire Transfer", "Online Payment Catalog"}
)

REVIEW_CATALOG_ALLOWED = frozenset(
    {
        "Full Board Review",
        "Expedited Review",
        "Exempt Determination",
        "Administrative Review",
    }
)
QUALITY_MET_ALLOWED = frozenset({"Yes", "No", "NA"})

DECISION_OUTCOME_ALLOWED = frozenset(
    {
        "Approved",
        "Approved with Conditions",
        "Modifications Required (Minor)",
        "Modifications Required (Major)",
        "Disapproved / Rejected",
    }
)

BANKING_CURRENCIES_ALLOWED = frozenset(
    {"USD", "INR", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "SGD", "AED"}
)


class IRBAdministrativeInfoCreateResponse(BaseModel):
    message: str
    irb_created: bool
    irb_id: Optional[int] = None


class IRBAdministrativeInfoLatestResponse(BaseModel):
    # IDs
    irb_id: int

    # Basic Demographics
    organization_type: str
    irb_name: Optional[str] = None
    iec_name: Optional[str] = None
    irb_type: Optional[str] = None
    iec_type: Optional[str] = None
    registration_id: Optional[str] = None
    fwa_number: Optional[str] = None
    ohrp_number: Optional[str] = None
    accreditation_body: Optional[str] = None
    accreditation_number: Optional[str] = None
    accreditation_expiry: Optional[date] = None
    irb_status: Optional[str] = None
    date_established: Optional[date] = None
    jurisdiction: Optional[str] = None

    # Address
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None
    office_hours: Optional[str] = None
    time_zone: Optional[str] = None

    # Contact - Primary
    primary_contact_name: Optional[str] = None
    primary_contact_job_title: Optional[str] = None
    primary_contact_email: Optional[str] = None
    primary_contact_phone: Optional[str] = None

    # Contact - Secondary
    secondary_contact_name: Optional[str] = None
    secondary_contact_job_title: Optional[str] = None
    secondary_contact_email: Optional[str] = None
    secondary_contact_phone: Optional[str] = None

    # Membership
    chair_name: Optional[str] = None
    vice_chair_name: Optional[str] = None
    number_of_members: Optional[int] = None
    number_of_alternates: Optional[int] = None

    quorum_required: Optional[bool] = None
    quorum_threshold_percent: Optional[float] = None
    quorum_minimum_members_present: Optional[int] = None

    full_board_meeting_frequency: Optional[str] = None
    usual_meeting_day: Optional[str] = None
    meeting_date: Optional[date] = None
    submission_deadline_before_meeting: Optional[str] = None

    submission_type: Optional[str] = None
    submission_date: Optional[date] = None

    submission_method: Optional[str] = None
    number_of_copies_required: Optional[int] = None
    submission_fee_currency: Optional[str] = None
    submission_fee_amount: Optional[float] = None
    payment_method: Optional[str] = None

    review_catalog: Optional[str] = None
    quality_met: Optional[str] = None
    irb_meeting_review_date: Optional[date] = None

    decision_outcome: Optional[str] = None
    decision_date: Optional[date] = None
    decision_letter_reference: Optional[str] = None
    approval_date: Optional[date] = None

    bank_name: Optional[str] = None
    bank_account_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    routing_swift_code: Optional[str] = None
    iban: Optional[str] = None
    banking_currency: Optional[str] = None
    invoice_address_alt: Optional[str] = None


def _assign_irb_admin_row_from_payload(
    row: IRBAdministrativeInfo,
    payload: IRBAdministrativeInfoCreate,
    org_type: str,
) -> None:
    row.organization_type = org_type
    row.irb_name = payload.irb_name
    row.iec_name = payload.iec_name
    row.irb_type = _normalize_irb_type(payload.irb_type)
    row.iec_type = _normalize_iec_type(payload.iec_type)
    row.registration_id = payload.registration_id
    row.fwa_number = payload.fwa_number
    row.ohrp_number = payload.ohrp_number
    row.accreditation_body = payload.accreditation_body
    row.accreditation_number = payload.accreditation_number
    row.accreditation_expiry = payload.accreditation_expiry
    row.irb_status = payload.irb_status
    row.date_established = payload.date_established
    row.jurisdiction = payload.jurisdiction
    row.address_line_1 = payload.address_line_1
    row.address_line_2 = payload.address_line_2
    row.city = payload.city
    row.state = payload.state
    row.zip_code = payload.zip_code
    row.country = payload.country
    row.office_hours = payload.office_hours
    row.time_zone = payload.time_zone
    row.primary_contact_name = payload.primary_contact_name
    row.primary_contact_job_title = payload.primary_contact_job_title
    row.primary_contact_email = (
        str(payload.primary_contact_email) if payload.primary_contact_email else None
    )
    row.primary_contact_phone = payload.primary_contact_phone
    row.secondary_contact_name = payload.secondary_contact_name
    row.secondary_contact_job_title = payload.secondary_contact_job_title
    row.secondary_contact_email = (
        str(payload.secondary_contact_email) if payload.secondary_contact_email else None
    )
    row.secondary_contact_phone = payload.secondary_contact_phone
    row.chair_name = payload.chair_name
    row.vice_chair_name = payload.vice_chair_name
    row.number_of_members = payload.number_of_members
    row.number_of_alternates = payload.number_of_alternates

    row.quorum_required = True if payload.quorum_required is True else False
    if payload.quorum_required is True:
        row.quorum_threshold_percent = payload.quorum_threshold_percent
        row.quorum_minimum_members_present = payload.quorum_minimum_members_present
    else:
        row.quorum_threshold_percent = None
        row.quorum_minimum_members_present = None

    row.full_board_meeting_frequency = payload.full_board_meeting_frequency.strip() if payload.full_board_meeting_frequency else None
    row.usual_meeting_day = payload.usual_meeting_day
    row.meeting_date = payload.meeting_date
    row.submission_deadline_before_meeting = payload.submission_deadline_before_meeting

    st = (payload.submission_type or "").strip()
    row.submission_type = st if st else None
    row.submission_date = payload.submission_date

    method = (payload.submission_method or "").strip()
    row.submission_method = method if method else None
    if method == "Hard Copy (Paper)":
        row.number_of_copies_required = payload.number_of_copies_required
    else:
        row.number_of_copies_required = None

    cur = (payload.submission_fee_currency or "").strip()
    row.submission_fee_currency = cur if cur else None
    row.submission_fee_amount = payload.submission_fee_amount if cur else None
    pm = (payload.payment_method or "").strip()
    row.payment_method = pm if pm else None

    rc = (payload.review_catalog or "").strip()
    row.review_catalog = rc if rc else None
    qm = (payload.quality_met or "").strip()
    row.quality_met = qm if qm else None
    row.irb_meeting_review_date = payload.irb_meeting_review_date

    dout = (payload.decision_outcome or "").strip()
    row.decision_outcome = dout if dout else None
    row.decision_date = payload.decision_date
    dlr = (payload.decision_letter_reference or "").strip()
    row.decision_letter_reference = dlr if dlr else None
    row.approval_date = payload.approval_date

    row.bank_name = (payload.bank_name or "").strip() or None
    row.bank_account_name = (payload.bank_account_name or "").strip() or None
    row.bank_account_number = (payload.bank_account_number or "").strip() or None
    row.routing_swift_code = (payload.routing_swift_code or "").strip() or None
    row.iban = (payload.iban or "").strip() or None
    bc = (payload.banking_currency or "").strip()
    row.banking_currency = bc if bc else None
    row.invoice_address_alt = (payload.invoice_address_alt or "").strip() or None


def _pct_to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@router.get("/irb-administrative-info/latest", response_model=Optional[IRBAdministrativeInfoLatestResponse])
async def get_latest_irb_administrative_info(
    irb_id: int = Query(..., ge=1),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the latest saved IRB Administrative Info for an IRB.
    """
    q = (
        select(IRBAdministrativeInfo)
        .where(IRBAdministrativeInfo.irb_id == int(irb_id))
        .order_by(IRBAdministrativeInfo.created_at.desc(), IRBAdministrativeInfo.id.desc())
        .limit(1)
    )
    res = await db.execute(q)
    row = res.scalar_one_or_none()
    if not row:
        return None

    return IRBAdministrativeInfoLatestResponse(
        irb_id=int(row.irb_id),
        organization_type=row.organization_type,
        irb_name=row.irb_name,
        iec_name=row.iec_name,
        irb_type=_normalize_irb_type(row.irb_type),
        iec_type=_normalize_iec_type(row.iec_type),
        registration_id=row.registration_id,
        fwa_number=row.fwa_number,
        ohrp_number=row.ohrp_number,
        accreditation_body=row.accreditation_body,
        accreditation_number=row.accreditation_number,
        accreditation_expiry=row.accreditation_expiry,
        irb_status=row.irb_status,
        date_established=row.date_established,
        jurisdiction=row.jurisdiction,
        address_line_1=row.address_line_1,
        address_line_2=row.address_line_2,
        city=row.city,
        state=row.state,
        zip_code=row.zip_code,
        country=row.country,
        office_hours=row.office_hours,
        time_zone=row.time_zone,
        primary_contact_name=row.primary_contact_name,
        primary_contact_job_title=row.primary_contact_job_title,
        primary_contact_email=row.primary_contact_email,
        primary_contact_phone=row.primary_contact_phone,
        secondary_contact_name=row.secondary_contact_name,
        secondary_contact_job_title=row.secondary_contact_job_title,
        secondary_contact_email=row.secondary_contact_email,
        secondary_contact_phone=row.secondary_contact_phone,
        chair_name=row.chair_name,
        vice_chair_name=row.vice_chair_name,
        number_of_members=row.number_of_members,
        number_of_alternates=row.number_of_alternates,
        quorum_required=row.quorum_required,
        quorum_threshold_percent=_pct_to_float(getattr(row, "quorum_threshold_percent", None)),
        quorum_minimum_members_present=getattr(row, "quorum_minimum_members_present", None),
        full_board_meeting_frequency=getattr(row, "full_board_meeting_frequency", None),
        usual_meeting_day=getattr(row, "usual_meeting_day", None),
        meeting_date=getattr(row, "meeting_date", None),
        submission_deadline_before_meeting=getattr(row, "submission_deadline_before_meeting", None),
        submission_type=getattr(row, "submission_type", None),
        submission_date=getattr(row, "submission_date", None),
        submission_method=getattr(row, "submission_method", None),
        number_of_copies_required=getattr(row, "number_of_copies_required", None),
        submission_fee_currency=getattr(row, "submission_fee_currency", None),
        submission_fee_amount=_pct_to_float(getattr(row, "submission_fee_amount", None)),
        payment_method=getattr(row, "payment_method", None),
        review_catalog=getattr(row, "review_catalog", None),
        quality_met=getattr(row, "quality_met", None),
        irb_meeting_review_date=getattr(row, "irb_meeting_review_date", None),
        decision_outcome=getattr(row, "decision_outcome", None),
        decision_date=getattr(row, "decision_date", None),
        decision_letter_reference=getattr(row, "decision_letter_reference", None),
        approval_date=getattr(row, "approval_date", None),
        bank_name=getattr(row, "bank_name", None),
        bank_account_name=getattr(row, "bank_account_name", None),
        bank_account_number=getattr(row, "bank_account_number", None),
        routing_swift_code=getattr(row, "routing_swift_code", None),
        iban=getattr(row, "iban", None),
        banking_currency=getattr(row, "banking_currency", None),
        invoice_address_alt=getattr(row, "invoice_address_alt", None),
    )


@router.post("/irb-administrative-info", response_model=IRBAdministrativeInfoCreateResponse)
async def create_irb_administrative_info(
    payload: IRBAdministrativeInfoCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Save IRB Administrative Info form data and ensure a corresponding global IRB exists.
    Admin info is 1:1 with IRB (unique irb_id).
    """
    if not payload.organization_type.strip():
        raise HTTPException(status_code=400, detail="organization_type is required")

    org_type = payload.organization_type.strip().upper()

    if org_type == "BOTH":
        raise HTTPException(
            status_code=400,
            detail="organization_type 'BOTH' is no longer supported. Use IRB or IEC.",
        )

    # Dynamic name requirements based on organization_type
    if org_type == "IRB" and (not payload.irb_name or not payload.irb_name.strip()):
        raise HTTPException(status_code=400, detail="irb_name is required for IRB organization_type")
    if org_type == "IEC" and (not payload.iec_name or not payload.iec_name.strip()):
        raise HTTPException(status_code=400, detail="iec_name is required for IEC organization_type")

    if org_type == "IRB":
        nt = _normalize_irb_type(payload.irb_type)
        if not nt:
            raise HTTPException(
                status_code=400,
                detail="irb_type must be Central, Institutional, or Independent.",
            )

    if org_type == "IEC":
        it = _normalize_iec_type(payload.iec_type)
        if not it:
            raise HTTPException(
                status_code=400,
                detail="iec_type must be Institutional or Independent.",
            )

    pname = (payload.primary_contact_name or "").strip()
    if not pname:
        raise HTTPException(status_code=400, detail="primary_contact_name is required")
    if not payload.primary_contact_email or not str(payload.primary_contact_email).strip():
        raise HTTPException(status_code=400, detail="primary_contact_email is required")
    pphone = (payload.primary_contact_phone or "").strip()
    if not pphone:
        raise HTTPException(status_code=400, detail="primary_contact_phone is required")

    state_val = (payload.state or "").strip()
    if not state_val:
        raise HTTPException(status_code=400, detail="state is required")
    zip_val = (payload.zip_code or "").strip()
    if not zip_val:
        raise HTTPException(status_code=400, detail="zip_code is required")

    if payload.quorum_required is True:
        p = payload.quorum_threshold_percent
        if p is None or not (0 < p <= 100):
            raise HTTPException(
                status_code=400,
                detail="When quorum is required, quorum_threshold_percent must be a number greater than 0 and at most 100.",
            )
        m = payload.quorum_minimum_members_present
        if m is None or int(m) < 1:
            raise HTTPException(
                status_code=400,
                detail="When quorum is required, quorum_minimum_members_present must be at least 1.",
            )

    freq = (payload.full_board_meeting_frequency or "").strip()
    if not freq:
        raise HTTPException(status_code=400, detail="full_board_meeting_frequency is required")
    if freq not in MEETING_FREQUENCY_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail="full_board_meeting_frequency must be one of: Weekly, Bi-weekly, Monthly, Quarterly, As needed.",
        )

    sub_t = (payload.submission_type or "").strip()
    if sub_t and sub_t not in SUBMISSION_TYPES_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail="submission_type must be one of: Initial, Amendment.",
        )

    sm = (payload.submission_method or "").strip()
    if sm and sm not in SUBMISSION_METHODS_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail="submission_method must be one of: Online – Portal, Email, Hard Copy (Paper), Regulatory System.",
        )
    if sm == "Hard Copy (Paper)":
        n = payload.number_of_copies_required
        if n is None or int(n) < 1:
            raise HTTPException(
                status_code=400,
                detail="When submission_method is Hard Copy (Paper), number_of_copies_required must be at least 1.",
            )

    fee_cur = (payload.submission_fee_currency or "").strip()
    fee_amt = payload.submission_fee_amount
    if fee_cur and fee_cur not in SUBMISSION_FEE_CURRENCIES_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail="submission_fee_currency must be one of: USD, INR, EUR.",
        )
    if (fee_amt is not None) != bool(fee_cur):
        raise HTTPException(
            status_code=400,
            detail="submission_fee_currency and submission_fee_amount must both be provided together, or both omitted.",
        )

    pm = (payload.payment_method or "").strip()
    if pm and pm not in PAYMENT_METHODS_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail="payment_method must be one of: Credit/Debit Card, Bank/Wire Transfer, Online Payment Catalog.",
        )

    rc = (payload.review_catalog or "").strip()
    if rc and rc not in REVIEW_CATALOG_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail="review_catalog must be one of: Full Board Review, Expedited Review, Exempt Determination, Administrative Review.",
        )
    qm_val = (payload.quality_met or "").strip()
    if qm_val and qm_val not in QUALITY_MET_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail="quality_met must be one of: Yes, No, NA.",
        )

    dout = (payload.decision_outcome or "").strip()
    if dout and dout not in DECISION_OUTCOME_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail="decision_outcome must be one of the allowed Decision / Outcome values.",
        )

    bcur = (payload.banking_currency or "").strip()
    if bcur and bcur not in BANKING_CURRENCIES_ALLOWED:
        raise HTTPException(
            status_code=400,
            detail="banking_currency must be a supported currency code (e.g. USD, INR, EUR).",
        )

    bn = (payload.bank_name or "").strip()
    if not bn:
        raise HTTPException(status_code=400, detail="bank_name is required")
    ban = (payload.bank_account_name or "").strip()
    if not ban:
        raise HTTPException(status_code=400, detail="bank_account_name is required")
    bnum = (payload.bank_account_number or "").strip()
    if not bnum:
        raise HTTPException(status_code=400, detail="bank_account_number is required")

    irb_created = False
    irb_id: Optional[int] = None

    try:
        async with db.begin():
            irb: Optional[IRB] = None
            if payload.irb_id is not None:
                existing = await db.execute(select(IRB).where(IRB.id == int(payload.irb_id)))
                irb = existing.scalar_one_or_none()
                if not irb:
                    raise HTTPException(status_code=404, detail="IRB not found")

            if not irb:
                # Create/find a global IRB (ethics board) by the primary name.
                primary_name = None
                if org_type == "IRB":
                    primary_name = payload.irb_name
                elif org_type == "IEC":
                    primary_name = payload.iec_name
                else:
                    raise HTTPException(status_code=400, detail="Invalid organization_type. Use IRB or IEC.")

                existing_by_name = await db.execute(select(IRB).where(IRB.name == primary_name))
                irb = existing_by_name.scalar_one_or_none()
                if not irb:
                    irb = IRB(name=primary_name)
                    db.add(irb)
                    irb_created = True
                await db.flush()

            assert irb is not None
            irb_id_int = int(irb.id)

            existing_info = await db.execute(
                select(IRBAdministrativeInfo).where(IRBAdministrativeInfo.irb_id == irb_id_int)
            )
            info_row = existing_info.scalar_one_or_none()
            if info_row:
                # UPDATING existing admin info → also update the IRB's name in the master table
                # This ensures the dropdown shows the updated name
                _assign_irb_admin_row_from_payload(info_row, payload, org_type)
                primary_name = payload.irb_name if org_type == "IRB" else payload.iec_name
                irb.name = primary_name
            else:
                info_row = IRBAdministrativeInfo(irb_id=irb_id_int)
                _assign_irb_admin_row_from_payload(info_row, payload, org_type)
                db.add(info_row)

        if irb is not None:
            irb_id = irb.id

        return IRBAdministrativeInfoCreateResponse(
            message="Saved successfully",
            irb_created=irb_created,
            irb_id=irb_id,
        )

    except HTTPException:
        # Do not wrap intended 4xx (e.g. 409 one-IRB-per-site, 404 IRB not found) as 500.
        # Do not call db.rollback() here: `async with db.begin()` already rolled back on exit.
        # A second rollback() can raise and get caught below as a bogus 500.
        raise
    except IntegrityError:
        # Handles race-condition duplicates on admin-info uniqueness and/or IRB creation.
        try:
            await db.rollback()
        except Exception:
            pass
        irb = None
        if payload.irb_id is not None:
            existing = await db.execute(select(IRB).where(IRB.id == int(payload.irb_id)))
            irb = existing.scalar_one_or_none()
        if not irb:
            # Re-resolve IRB by primary name
            org_type = payload.organization_type.strip().upper()
            primary_name = payload.irb_name if org_type == "IRB" else payload.iec_name
            existing_by_name = await db.execute(select(IRB).where(IRB.name == primary_name))
            irb = existing_by_name.scalar_one_or_none()
        return IRBAdministrativeInfoCreateResponse(
            message="Saved successfully",
            irb_created=False,
            irb_id=irb.id if irb else None,
        )
    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to save IRB administrative info: {str(e)}")

