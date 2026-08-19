"""
app.models package.

Domain split of the former app/models.py (1,451 lines, 69 classes). Each domain
file holds its own SQLAlchemy models and enums. This __init__ re-exports every
public name so existing imports keep working:

    from app.models import Conversation, Agreement, User   # still works

When adding a new model, place it in the right domain file and add it to
__all__ below. Do not let this file grow into a god-module - it is purely an
import surface.
"""

from app.models._types import EnumValueType

from app.models.conversation import (
    AccessType,
    Attachment,
    Conversation,
    ConversationAccess,
    ConversationAccessLevel,
    Message,
    MessageChannel,
    MessageDirection,
    MessageStatus,
    ThreadFromConversation,
)
from app.models.thread import (
    Thread,
    ThreadAttachment,
    ThreadMessage,
    ThreadParticipant,
)
from app.models.user import (
    User,
    UserProfile,
    UserRole,
    UserRoleAssignment,
    UserSite,
)
from app.models.audit import AuditLog
from app.models.user_profile import (
    Event,
    IISStudy,
    RDStudy,
)
from app.models.study import Study, StudySite
from app.models.site import Site
from app.models.site_status import (
    PrimarySiteStatus,
    SiteProfile,
    SiteStatus,
    SiteStatusHistory,
)
from app.models.workflow import (
    DocumentCategory,
    DocumentType,
    ReviewStatus,
    SiteWorkflowStep,
    StepStatus,
    WorkflowStepName,
)
from app.models.chat import ChatDocument, ChatMessage
from app.models.site_document import SiteDocument
from app.models.irb import (
    IRB,
    IRBAdministrativeInfo,
    IRBRequiredDocument,
    SiteIRBMapping,
)
from app.models.feasibility import (
    FeasibilityAttachment,
    FeasibilityRequest,
    FeasibilityRequestStatus,
    FeasibilityResponse,
    ProjectFeasibilityCustomQuestion,
)
from app.models.agreement import (
    Agreement,
    AgreementChange,
    AgreementComment,
    AgreementDocument,
    AgreementDocumentComment,
    AgreementInlineComment,
    AgreementInternalSignature,
    AgreementReviewDocument,
    AgreementReviewerSignature,
    AgreementReviewOtp,
    AgreementReviewToken,
    AgreementNegotiationRound,
    AgreementSignatureSource,
    AgreementSignedDocument,
    AgreementSigner,
    AgreementSigningOtp,
    AgreementSigningToken,
    AgreementStatus,
    CommentStatus,
    CommentType,
    CompositionMode,
    StudyTemplate,
    TemplateType,
)
from app.models.clause import (
    Clause,
    ClauseVersion,
    ClauseVersionStatus,
    LockPolicy,
    TemplateClause,
)
from app.modules.agreements.types.cta.models import CTAAssignment, CTAPlaceholderMapping  # noqa: E402
from app.modules.workflows.models import (  # noqa: E402
    WorkflowAuditEntry,
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowInstance,
)
from app.modules.assistant.memory.models import (  # noqa: E402
    AssistantMemory,
    AssistantTurn,
)
from app.modules.assistant.live_eval.models import LiveEvalScore  # noqa: E402

__all__ = [
    # _types
    "EnumValueType",
    # conversation
    "AccessType",
    "Attachment",
    "Conversation",
    "ConversationAccess",
    "ConversationAccessLevel",
    "Message",
    "MessageChannel",
    "MessageDirection",
    "MessageStatus",
    "ThreadFromConversation",
    # thread
    "Thread",
    "ThreadAttachment",
    "ThreadMessage",
    "ThreadParticipant",
    # user
    "User",
    "UserProfile",
    "UserRole",
    "UserRoleAssignment",
    "UserSite",
    # audit
    "AuditLog",
    # user_profile (HCP / events)
    "Event",
    "IISStudy",
    "RDStudy",
    # study
    "Study",
    "StudySite",
    # site
    "Site",
    # site_status
    "PrimarySiteStatus",
    "SiteProfile",
    "SiteStatus",
    "SiteStatusHistory",
    # workflow
    "DocumentCategory",
    "DocumentType",
    "ReviewStatus",
    "SiteWorkflowStep",
    "StepStatus",
    "WorkflowStepName",
    # chat
    "ChatDocument",
    "ChatMessage",
    # site_document
    "SiteDocument",
    # irb
    "IRB",
    "IRBAdministrativeInfo",
    "IRBRequiredDocument",
    "SiteIRBMapping",
    # feasibility
    "FeasibilityAttachment",
    "FeasibilityRequest",
    "FeasibilityRequestStatus",
    "FeasibilityResponse",
    "ProjectFeasibilityCustomQuestion",
    # agreement
    "Agreement",
    "AgreementChange",
    "AgreementComment",
    "AgreementDocument",
    "AgreementDocumentComment",
    "AgreementInlineComment",
    "AgreementInternalSignature",
    "AgreementReviewDocument",
    "AgreementReviewerSignature",
    "AgreementReviewOtp",
    "AgreementReviewToken",
    "AgreementNegotiationRound",
    "AgreementSignatureSource",
    "AgreementSignedDocument",
    "AgreementSigner",
    "AgreementSigningOtp",
    "AgreementSigningToken",
    "AgreementStatus",
    "CommentStatus",
    "CommentType",
    "CompositionMode",
    "StudyTemplate",
    "TemplateType",
    # clause library
    "Clause",
    "ClauseVersion",
    "ClauseVersionStatus",
    "LockPolicy",
    "TemplateClause",
    # cta (new workflow models)
    "CTAAssignment",
    "CTAPlaceholderMapping",
    # workflow platform (generic engine)
    "WorkflowDefinition",
    "WorkflowDefinitionVersion",
    "WorkflowInstance",
    "WorkflowAuditEntry",
    # orbit derived memory
    "AssistantMemory",
    "AssistantTurn",
    # orbit live evals (append-only score store)
    "LiveEvalScore",
]
