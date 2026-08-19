"""IRB (Institutional Review Board) entities and site mappings."""
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class IRBAdministrativeInfo(Base):
    __tablename__ = "irb_administrative_info"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Refactored: IRB admin info is owned by a global IRB entity (no site/study).
    irb_id = Column(Integer, ForeignKey("irbs.id", ondelete="CASCADE"), nullable=True, unique=True, index=True)

    # Basic Demographics
    organization_type = Column(Text, nullable=False)
    irb_name = Column(Text, nullable=True)
    iec_name = Column(Text, nullable=True)
    irb_type = Column(Text, nullable=True)
    iec_type = Column(Text, nullable=True)
    registration_id = Column(Text, nullable=True)
    fwa_number = Column(Text, nullable=True)
    ohrp_number = Column(Text, nullable=True)
    accreditation_body = Column(Text, nullable=True)
    accreditation_number = Column(Text, nullable=True)
    accreditation_expiry = Column(Date, nullable=True)
    irb_status = Column(Text, nullable=True)
    date_established = Column(Date, nullable=True)
    jurisdiction = Column(Text, nullable=True)

    # Address
    address_line_1 = Column(Text, nullable=True)
    address_line_2 = Column(Text, nullable=True)
    city = Column(Text, nullable=True)
    state = Column(Text, nullable=True)
    zip_code = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    office_hours = Column(Text, nullable=True)
    time_zone = Column(Text, nullable=True)

    # Contact - Primary
    primary_contact_name = Column(Text, nullable=True)
    primary_contact_job_title = Column(Text, nullable=True)
    primary_contact_email = Column(Text, nullable=True)
    primary_contact_phone = Column(Text, nullable=True)

    # Contact - Secondary
    secondary_contact_name = Column(Text, nullable=True)
    secondary_contact_job_title = Column(Text, nullable=True)
    secondary_contact_email = Column(Text, nullable=True)
    secondary_contact_phone = Column(Text, nullable=True)

    # Membership
    chair_name = Column(Text, nullable=True)
    vice_chair_name = Column(Text, nullable=True)
    number_of_members = Column(Integer, nullable=True)
    number_of_alternates = Column(Integer, nullable=True)

    quorum_required = Column(Boolean, nullable=True)
    quorum_threshold_percent = Column(Numeric(5, 2), nullable=True)
    quorum_minimum_members_present = Column(Integer, nullable=True)

    full_board_meeting_frequency = Column(Text, nullable=True)
    usual_meeting_day = Column(Text, nullable=True)
    meeting_date = Column(Date, nullable=True)
    submission_deadline_before_meeting = Column(Text, nullable=True)

    submission_type = Column(Text, nullable=True)
    submission_date = Column(Date, nullable=True)

    submission_method = Column(Text, nullable=True)
    number_of_copies_required = Column(Integer, nullable=True)
    submission_fee_currency = Column(Text, nullable=True)
    submission_fee_amount = Column(Numeric(14, 2), nullable=True)
    payment_method = Column(Text, nullable=True)

    review_catalog = Column(Text, nullable=True)
    quality_met = Column(Text, nullable=True)
    irb_meeting_review_date = Column(Date, nullable=True)

    decision_outcome = Column(Text, nullable=True)
    decision_date = Column(Date, nullable=True)
    decision_letter_reference = Column(Text, nullable=True)
    approval_date = Column(Date, nullable=True)

    bank_name = Column(Text, nullable=True)
    bank_account_name = Column(Text, nullable=True)
    bank_account_number = Column(Text, nullable=True)
    routing_swift_code = Column(Text, nullable=True)
    iban = Column(Text, nullable=True)
    banking_currency = Column(Text, nullable=True)
    invoice_address_alt = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    irb = relationship("IRB", foreign_keys=[irb_id])


class IRB(Base):
    __tablename__ = "irbs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    unique_code = Column(Text, nullable=True, unique=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SiteIRBMapping(Base):
    __tablename__ = "site_irb_mapping"
    __table_args__ = (UniqueConstraint("site_id", name="uq_site_irb_mapping_site"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id", ondelete="CASCADE"), nullable=False, index=True)
    irb_id = Column(Integer, ForeignKey("irbs.id", ondelete="CASCADE"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    irb = relationship("IRB", foreign_keys=[irb_id])
    site = relationship("Site", foreign_keys=[site_id])


class IRBRequiredDocument(Base):
    __tablename__ = "irb_required_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    irb_id = Column(Integer, ForeignKey("irbs.id", ondelete="CASCADE"), nullable=False, index=True)
    document_name = Column(Text, nullable=False)
    is_mandatory = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    irb = relationship("IRB", foreign_keys=[irb_id])
