"""Agreement workflow models: templates, agreements, comments, documents, signatures, OTPs, review/signing tokens."""
import enum
import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base
from app.models._types import EnumValueType


class AgreementStatus(str, enum.Enum):
    """Status enum for Agreement workflow."""
    DRAFT = "DRAFT"
    UNDER_REVIEW = "UNDER_REVIEW"
    UNDER_NEGOTIATION = "UNDER_NEGOTIATION"
    REVIEWED_AND_SIGNED = "REVIEWED_AND_SIGNED"
    FULLY_SIGNED = "FULLY_SIGNED"
    READY_FOR_SIGNATURE = "READY_FOR_SIGNATURE"
    SENT_FOR_SIGNATURE = "SENT_FOR_SIGNATURE"
    AWAITING_INTERNAL_REVIEW = "AWAITING_INTERNAL_REVIEW"
    INTERNAL_REVIEW_APPROVED = "INTERNAL_REVIEW_APPROVED"
    AWAITING_SPONSOR_SIGNATURE = "AWAITING_SPONSOR_SIGNATURE"
    EXECUTED = "EXECUTED"
    CLOSED = "CLOSED"


class AgreementSignatureSource(str, enum.Enum):
    ZOHO = "ZOHO"
    INTERNAL = "INTERNAL"


class CommentType(str, enum.Enum):
    """Comment type enum for Agreement comments."""
    INTERNAL = "INTERNAL"
    EXTERNAL = "EXTERNAL"
    SYSTEM = "SYSTEM"


class TemplateType(str, enum.Enum):
    """Template type enum for StudyTemplate."""
    CDA = "CDA"
    CTA = "CTA"
    BUDGET = "BUDGET"
    OTHER = "OTHER"


class CompositionMode(str, enum.Enum):
    """How the template content is sourced.

    DOCX_UPLOAD    — legacy: a DOCX file is the source of truth (default for
                     all pre-existing templates; never broken by this change).
    CLAUSE_COMPOSED — new: the template is built from ordered TemplateClause
                     rows; DOCX is an export artifact, NOT the source.
    """
    DOCX_UPLOAD     = "DOCX_UPLOAD"
    CLAUSE_COMPOSED = "CLAUSE_COMPOSED"


class CommentStatus(str, enum.Enum):
    PENDING  = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    MODIFIED = "modified"


class StudyTemplate(Base):
    """
    Template model for storing reusable document templates per study.
    Templates store TipTap JSON content for agreement documents.
    """
    __tablename__ = "study_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id"), nullable=False)
    template_name = Column(String(255), nullable=False)
    template_type = Column(EnumValueType(TemplateType, "template_type", 50), nullable=False)
    template_content = Column(JSON, nullable=True)  # TipTap JSON content (legacy, nullable for DOCX-only templates)
    template_file_path = Column(Text, nullable=True)  # Blob name (Azure) or local path
    template_file_url = Column(Text, nullable=True)  # Azure Blob Storage URL (set when stored in Azure)
    document_html = Column(Text, nullable=True)  # Legacy HTML field (deprecated, kept for migration)
    placeholder_config = Column(JSON, nullable=True)  # Configuration for placeholder editability
    field_mappings = Column(JSON, nullable=True)  # Dynamic field mappings
    # Clause Builder: where clauses get spliced into the original DOCX at agreement
    # generation. List of {after_block, clause_id, clause_version_id, clause_title}.
    # after_block = index into the original DOCX body blocks (paragraphs + tables);
    # -1 means "before the first block". Original DOCX is never modified — clauses are
    # spliced into a clone at generation, preserving all surrounding formatting.
    clause_insertions = Column(JSON, nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(String(10), nullable=False, default='true')  # 'true' or 'false' as string
    # Added by clause library migration. Default DOCX_UPLOAD keeps all pre-existing
    # rows working unchanged; only new clause-composed templates use CLAUSE_COMPOSED.
    composition_mode = Column(
        EnumValueType(CompositionMode, "composition_mode", 30),
        nullable=False,
        default=CompositionMode.DOCX_UPLOAD,
    )

    study = relationship("Study", foreign_keys=[study_id])
    agreement_documents = relationship("AgreementDocument", back_populates="template")

    __table_args__ = (
        {"comment": "Reusable TipTap JSON document templates for study agreements"}
    )


class Agreement(Base):
    """Agreement model for tracking contract/agreement workflow per site."""
    __tablename__ = "agreements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False)
    # Optional StudySite join – enables explicit (study + site) mapping without removing legacy fields.
    study_site_id = Column(UUID(as_uuid=True), ForeignKey("study_sites.id"), nullable=True)
    # NEW: Explicit study scoping for agreements (Study + Site pair)
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id"), nullable=True)
    title = Column(String(500), nullable=False)
    status = Column(EnumValueType(AgreementStatus, "agreement_status", 50), nullable=False, default=AgreementStatus.DRAFT)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_legacy = Column(String(10), nullable=False, default='false')  # 'true' or 'false' - marks old file-based agreements
    zoho_request_id = Column(String(255), nullable=True)  # Zoho Sign request ID
    signature_status = Column(String(50), nullable=True)  # 'SENT', 'COMPLETED', 'DECLINED', 'EXPIRED'
    signature_source = Column(
        EnumValueType(AgreementSignatureSource, "agreement_signature_source", 20),
        nullable=False,
        default=AgreementSignatureSource.ZOHO,
    )
    # NEW: Agreement type (CDA / CTA / BUDGET / OTHER) for uniqueness per study+site+type
    agreement_type = Column(EnumValueType(TemplateType, "template_type", 50), nullable=True)
    # Edit lock fields for preventing concurrent editing
    editing_user_id = Column(String(255), nullable=True)
    editing_started_at = Column(DateTime(timezone=True), nullable=True)
    # CTA amendments: when set, this Agreement is an amendment of the parent
    # Agreement referenced here. Parent stays EXECUTED + locked; the amendment
    # row goes through its own full negotiation+sign lifecycle.
    amendment_of_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=True)

    site = relationship("Site", foreign_keys=[site_id])
    study_site = relationship("StudySite", foreign_keys=[study_site_id])
    comments = relationship("AgreementComment", back_populates="agreement", primaryjoin="Agreement.id == AgreementComment.agreement_id", cascade="all, delete-orphan", order_by="AgreementComment.created_at")
    documents = relationship("AgreementDocument", back_populates="agreement", primaryjoin="Agreement.id == AgreementDocument.agreement_id", cascade="all, delete-orphan", order_by="AgreementDocument.version_number")
    signed_documents = relationship(
        "AgreementSignedDocument",
        back_populates="agreement",
        foreign_keys="AgreementSignedDocument.agreement_id",
        cascade="all, delete-orphan",
    )
    review_documents = relationship("AgreementReviewDocument", back_populates="agreement", cascade="all, delete-orphan")
    reviewer_signatures = relationship("AgreementReviewerSignature", back_populates="agreement", cascade="all, delete-orphan")
    review_otps = relationship("AgreementReviewOtp", back_populates="agreement", cascade="all, delete-orphan")
    internal_signatures = relationship("AgreementInternalSignature", back_populates="agreement", cascade="all, delete-orphan")
    signing_otps = relationship("AgreementSigningOtp", back_populates="agreement", cascade="all, delete-orphan")
    signing_tokens = relationship("AgreementSigningToken", back_populates="agreement", cascade="all, delete-orphan")
    signers = relationship(
        "AgreementSigner",
        back_populates="agreement",
        cascade="all, delete-orphan",
        order_by="AgreementSigner.sign_order",
    )
    negotiation_rounds = relationship(
        "AgreementNegotiationRound",
        back_populates="agreement",
        cascade="all, delete-orphan",
        order_by="AgreementNegotiationRound.round_number",
    )
    # Amendments of this Agreement; parent_agreement is the inverse.
    amendments = relationship(
        "Agreement",
        backref="parent_agreement",
        remote_side="Agreement.id",
        foreign_keys=[amendment_of_id],
    )


# AgreementNegotiationRound is owned by the CTA workflow and lives under
# app/modules/agreements/types/cta/models.py. Re-imported here so that
# existing callers using `from app.models import AgreementNegotiationRound`
# (notably app/models/__init__.py) keep working.
from app.modules.agreements.types.cta.models import AgreementNegotiationRound  # noqa: F401, E402


class AgreementSigner(Base):
    """Ordered signer list for sequential multi-signer e-sign flow.

    See migrations/add_agreement_signers_table.sql for the schema. One row per
    (agreement, role) and per (agreement, sign_order). The sender assembles this
    list at send-time; the OTP dispatcher walks it in sign_order to drive the
    sequential email loop.
    """

    __tablename__ = "agreement_signers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    role = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    sign_order = Column(Integer, nullable=False)
    placeholder_name = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="pending")  # pending | invited | signed | declined
    signed_at = Column(DateTime(timezone=True), nullable=True)
    invited_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    agreement = relationship("Agreement", back_populates="signers", foreign_keys=[agreement_id])

    __table_args__ = (
        UniqueConstraint("agreement_id", "sign_order", name="uq_agreement_signers_agreement_order"),
        UniqueConstraint("agreement_id", "role", name="uq_agreement_signers_agreement_role"),
        {"comment": "Per-agreement ordered signer list for sequential multi-signer e-sign flow"},
    )


class AgreementComment(Base):
    """Comment model for Agreement discussions and system logging."""
    __tablename__ = "agreement_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    version_id = Column(UUID(as_uuid=True), nullable=True)
    comment_type = Column(EnumValueType(CommentType, "comment_type", 50), nullable=False)
    content = Column(Text, nullable=False)
    created_by = Column(String(255), nullable=True)  # Nullable for system comments
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agreement = relationship("Agreement", back_populates="comments", foreign_keys=[agreement_id])


class AgreementDocument(Base):
    """
    Template-based document model for Agreement.
    Stores TipTap JSON documents created from StudyTemplate.
    """
    __tablename__ = "agreement_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    document_content = Column(JSON, nullable=True)  # TipTap JSON content (legacy, nullable for DOCX-only documents)
    document_html = Column(Text, nullable=True)  # Legacy HTML field (deprecated, kept for migration)
    document_file_path = Column(Text, nullable=True)  # Blob name (Azure) or local path
    document_file_url = Column(Text, nullable=True)  # Azure Blob Storage URL
    created_from_template_id = Column(UUID(as_uuid=True), ForeignKey("study_templates.id"), nullable=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_signed_version = Column(String(10), nullable=False, default='false')  # 'true' or 'false' as string

    agreement = relationship("Agreement", back_populates="documents", foreign_keys=[agreement_id])
    template = relationship("StudyTemplate", back_populates="agreement_documents", foreign_keys=[created_from_template_id])
    inline_comments = relationship("AgreementInlineComment", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint('agreement_id', 'version_number', name='uq_agreement_document_version'),
        {"comment": "Template-based TipTap JSON documents for agreements."}
    )


class AgreementInlineComment(Base):
    """
    Inline comment model for Agreement documents.
    Comments are attached to specific positions in TipTap documents.
    """
    __tablename__ = "agreement_inline_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("agreement_documents.id"), nullable=False)
    comment_text = Column(Text, nullable=False)
    position_reference = Column(JSON, nullable=True)  # TipTap position/mark reference
    comment_type = Column(EnumValueType(CommentType, "comment_type", 50), nullable=False)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agreement = relationship("Agreement", foreign_keys=[agreement_id])
    document = relationship("AgreementDocument", back_populates="inline_comments", foreign_keys=[document_id])

    __table_args__ = (
        {"comment": "Inline comments attached to specific positions in agreement documents"}
    )


class AgreementSignedDocument(Base):
    """Model for storing signed PDF documents from Zoho Sign."""
    __tablename__ = "agreement_signed_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    file_path = Column(String(500), nullable=False)  # Path to signed PDF file
    signed_at = Column(DateTime(timezone=True), nullable=True)  # When document was signed (from Zoho)
    downloaded_from_zoho_at = Column(DateTime(timezone=True), server_default=func.now())  # When we downloaded it
    zoho_request_id = Column(String(255), nullable=True)  # Zoho Sign request ID for reference

    agreement = relationship(
        "Agreement",
        back_populates="signed_documents",
        foreign_keys=[agreement_id],
    )

    __table_args__ = (
        {"comment": "Signed PDF documents downloaded from Zoho Sign for agreements"}
    )


class AgreementReviewToken(Base):
    """Model for storing secure review tokens for external site access to agreements."""
    __tablename__ = "agreement_review_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    token = Column(String(255), nullable=False, unique=True, index=True)  # Secure token for review link
    recipient_email = Column(String(255), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)  # Token expiration time
    created_by = Column(String(255), nullable=True)  # User who created the review link
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    used_at = Column(DateTime(timezone=True), nullable=True)  # When token was first used
    is_active = Column(String(10), nullable=False, default='true')  # 'true' or 'false' - can be revoked

    agreement = relationship("Agreement", foreign_keys=[agreement_id])

    __table_args__ = (
        {"comment": "Secure tokens for external site review access to agreements"}
    )


class AgreementReviewOtp(Base):
    """One-time passwords used by external reviewers to sign and return an agreement."""
    __tablename__ = "agreement_review_otps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    review_token_id = Column(UUID(as_uuid=True), ForeignKey("agreement_review_tokens.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("agreement_documents.id"), nullable=False)
    email = Column(String(255), nullable=False)
    otp_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_sent_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(String(10), nullable=False, default='true')

    agreement = relationship("Agreement", back_populates="review_otps", foreign_keys=[agreement_id])
    review_token = relationship("AgreementReviewToken", foreign_keys=[review_token_id])
    document = relationship("AgreementDocument", foreign_keys=[document_id])

    __table_args__ = (
        {"comment": "OTP challenges for external reviewer sign-and-send-back flow"}
    )


class AgreementInternalSignature(Base):
    """Generic internal e-signature record (21 CFR Part 11 audit trail entity)."""
    __tablename__ = "agreement_internal_signatures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("agreement_documents.id"), nullable=False)
    role = Column(String(50), nullable=False)  # "reviewer" | "site"
    email = Column(String(255), nullable=False)
    meaning = Column(String(255), nullable=False)
    auth_method = Column(String(50), nullable=False, default="otp")
    version = Column(Integer, nullable=False)
    ip_address = Column(String(100), nullable=True)
    document_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agreement = relationship("Agreement", back_populates="internal_signatures", foreign_keys=[agreement_id])
    document = relationship("AgreementDocument", foreign_keys=[document_id])

    __table_args__ = (
        {"comment": "Internal multi-signer signature records for agreements"}
    )


class AgreementSigningOtp(Base):
    """OTP challenges for internal multi-signer agreement signing (site signer, etc.)."""
    __tablename__ = "agreement_signing_otps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("agreement_documents.id"), nullable=False)
    role = Column(String(50), nullable=False)  # "reviewer" | "site"
    email = Column(String(255), nullable=False)
    otp_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_sent_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(String(10), nullable=False, default='true')

    agreement = relationship("Agreement", back_populates="signing_otps", foreign_keys=[agreement_id])
    document = relationship("AgreementDocument", foreign_keys=[document_id])

    __table_args__ = (
        {"comment": "OTP challenges for internal agreement signing steps"}
    )


class AgreementSigningToken(Base):
    """Secure email-link token for final agreement signing access."""
    __tablename__ = "agreement_signing_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    token = Column(String(255), nullable=False, unique=True, index=True)
    role = Column(String(50), nullable=False, default="site")
    recipient_email = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    used_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(String(10), nullable=False, default='true')

    agreement = relationship("Agreement", back_populates="signing_tokens", foreign_keys=[agreement_id])

    __table_args__ = (
        {"comment": "Secure tokens for external/internal signer email-link access to agreements"}
    )


class AgreementReviewerSignature(Base):
    """Signature/audit record for an external reviewer approval completed with OTP."""
    __tablename__ = "agreement_reviewer_signatures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("agreement_documents.id"), nullable=False)
    user_email = Column(String(255), nullable=False)
    role = Column(String(100), nullable=False, default="external_reviewer")
    version = Column(Integer, nullable=False)
    meaning = Column(String(255), nullable=False)
    auth_method = Column(String(50), nullable=False, default="otp")
    ip_address = Column(String(100), nullable=True)
    document_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    agreement = relationship("Agreement", back_populates="reviewer_signatures", foreign_keys=[agreement_id])
    document = relationship("AgreementDocument", foreign_keys=[document_id])

    __table_args__ = (
        {"comment": "External reviewer signature records created via OTP approval"}
    )


class AgreementChange(Base):
    """Model for tracking document changes made during review/negotiation."""
    __tablename__ = "agreement_changes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    document_version_id = Column(UUID(as_uuid=True), ForeignKey("agreement_documents.id"), nullable=False)  # Version where change was made
    previous_version_id = Column(UUID(as_uuid=True), ForeignKey("agreement_documents.id"), nullable=True)  # Previous version for comparison
    change_type = Column(String(50), nullable=False)  # 'ADDED', 'DELETED', 'MODIFIED'
    section_reference = Column(String(500), nullable=True)  # Reference to section/clause (e.g., "Section 3.2")
    old_text = Column(Text, nullable=True)  # Text that was removed/modified
    new_text = Column(Text, nullable=True)  # Text that was added/modified
    paragraph_index = Column(Integer, nullable=True)  # Paragraph index in document
    table_index = Column(Integer, nullable=True)  # Table index if change is in table
    row_index = Column(Integer, nullable=True)  # Row index if change is in table
    cell_index = Column(Integer, nullable=True)  # Cell index if change is in table
    created_by = Column(String(255), nullable=True)  # User who made the change
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_external_change = Column(String(10), nullable=False, default='false')  # 'true' if change made by external site user
    is_accepted = Column(String(10), nullable=False, default='false')  # 'true' if change was accepted by internal user
    accepted_by = Column(String(255), nullable=True)  # User who accepted the change
    accepted_at = Column(DateTime(timezone=True), nullable=True)

    agreement = relationship("Agreement", foreign_keys=[agreement_id])
    document_version = relationship("AgreementDocument", foreign_keys=[document_version_id])
    previous_version = relationship("AgreementDocument", foreign_keys=[previous_version_id])

    __table_args__ = (
        {"comment": "Track document changes during agreement review and negotiation"}
    )


class AgreementReviewDocument(Base):
    """
    Model for storing review copies of agreement documents.
    External reviewers edit these copies, not the main AgreementDocument.
    """
    __tablename__ = "agreement_review_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    review_token_id = Column(UUID(as_uuid=True), ForeignKey("agreement_review_tokens.id"), nullable=False)
    base_version_id = Column(UUID(as_uuid=True), ForeignKey("agreement_documents.id"), nullable=False)  # Main document version this review copy is based on
    review_file_path = Column(Text, nullable=False)  # Path to review copy DOCX file
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_submitted = Column(String(10), nullable=False, default='false')  # 'true' if review has been submitted
    submitted_at = Column(DateTime(timezone=True), nullable=True)  # When review was submitted
    # Save Document feature fields
    saved_review_url = Column(Text, nullable=True)  # URL to the saved review document in Azure
    saved_review_path = Column(Text, nullable=True)  # Blob path to the saved review document
    saved_at = Column(DateTime(timezone=True), nullable=True)  # When the review document was last saved

    agreement = relationship("Agreement", foreign_keys=[agreement_id])
    review_token = relationship("AgreementReviewToken", foreign_keys=[review_token_id])
    base_version = relationship("AgreementDocument", foreign_keys=[base_version_id])

    __table_args__ = (
        {"comment": "Review copies of agreement documents for external site editing"}
    )


class AgreementDocumentComment(Base):
    """
    Stores OnlyOffice comments extracted from a review copy of an agreement
    document (AgreementReviewDocument).
    """
    __tablename__ = "agreement_document_comments"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # OOXML comment id — used to upsert when the DOCX is re-saved
    comment_id         = Column(String(50),  nullable=False)
    review_document_id = Column(UUID(as_uuid=True),
                                ForeignKey("agreement_review_documents.id", ondelete="CASCADE"),
                                nullable=True)   # NULL for manually created internal replies
    agreement_id       = Column(UUID(as_uuid=True),
                                ForeignKey("agreements.id", ondelete="CASCADE"),
                                nullable=False)
    author_email       = Column(String(255), nullable=False, default="")
    comment_text       = Column(Text,        nullable=False, default="")
    referenced_text    = Column(Text,        nullable=True)   # quoted text from the document
    oo_date            = Column(String(50),  nullable=True)   # ISO string from OOXML
    status             = Column(
                            String(20),
                            nullable=False,
                            default=CommentStatus.PENDING,
                        )
    # Self-referential: a reply row points to its parent comment's id (UUID PK)
    parent_comment_id  = Column(UUID(as_uuid=True),
                                ForeignKey("agreement_document_comments.id", ondelete="SET NULL"),
                                nullable=True)
    is_internal_reply  = Column(String(10), nullable=False, default='false')  # 'true'/'false'
    created_at         = Column(DateTime(timezone=True), server_default=func.now())
    updated_at         = Column(DateTime(timezone=True), server_default=func.now(),
                                onupdate=func.now())

    agreement       = relationship("Agreement",               foreign_keys=[agreement_id])
    review_document = relationship("AgreementReviewDocument", foreign_keys=[review_document_id])
    # Self-referential: parent ← child replies
    replies = relationship(
        "AgreementDocumentComment",
        primaryjoin="AgreementDocumentComment.parent_comment_id == AgreementDocumentComment.id",
        foreign_keys=[parent_comment_id],
        lazy="select",
        uselist=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "comment_id", "review_document_id",
            name="uq_agreement_doc_comment_oo_id",
        ),
        {"comment": "OnlyOffice review comments extracted from agreement review documents"},
    )
