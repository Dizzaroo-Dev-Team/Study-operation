"""
app.schemas package.

Domain split of the former app/schemas.py (1,290 lines, 100+ Pydantic classes).
Re-exports every public name so existing imports keep working:

    from app.schemas import ConversationCreate, AgreementResponse   # still works

When adding a new schema, place it in the right domain file and add it to
__all__ below. Do not let this file grow into a god-module - it is purely an
import surface.
"""

from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationStateUpdate,
    ConversationWithMessages,
    MessageCreate,
    MessageDecisionUpdate,
    MessageResponse,
    WebhookPayload,
    WebSocketEvent,
    WebSocketMessage,
)
from app.schemas.ai import (
    AICheckMessageIssue,
    AICheckMessageRequest,
    AICheckMessageResponse,
    AIComposeReplyDrafts,
    AIComposeReplyRequest,
    AIComposeReplyResponse,
    ResearchPaperSummary,
)
from app.schemas.attachment import AttachmentResponse
from app.schemas.thread import (
    CombineThreadsRequest,
    CreateThreadFromConversationRequest,
    ThreadAttachmentResponse,
    ThreadCombinationSuggestion,
    ThreadCreate,
    ThreadMessageCreate,
    ThreadMessageResponse,
    ThreadParticipantCreate,
    ThreadParticipantResponse,
    ThreadResponse,
    ThreadSimilarityAnalysis,
    ThreadWithMessages,
)
from app.schemas.user import (
    ConversationAccessCreate,
    ConversationAccessResponse,
    GrantAccessRequest,
    Token,
    UpdateConversationAccessRequest,
    UserCreate,
    UserLogin,
    UserResponse,
    UserRoleAssignmentCreate,
    UserRoleAssignmentResponse,
    UserSignup,
)
from app.schemas.user_profile import (
    EventCreate,
    EventResponse,
    IISStudyCreate,
    IISStudyResponse,
    RDStudyCreate,
    RDStudyResponse,
    UserProfileCreate,
    UserProfileResponse,
)
from app.schemas.chat import (
    ChatDocumentResponse,
    ChatMessageCreate,
    ChatMessageResponse,
)
from app.schemas.task import (
    TaskCreate,
    TaskLinks,
    TaskResponse,
    TaskUpdate,
)
from app.schemas.site_status import (
    SECONDARY_STATUS_MODELS,
    ActiveNotRecruitingMetadata,
    ClosedMetadata,
    CompletedMetadata,
    CountryStatusSummary,
    InitiatedNotRecruitingMetadata,
    InitiatingMetadata,
    RecruitingMetadata,
    SiteStatusDetail,
    SiteStatusHistoryEntry,
    StartupMetadata,
    UnderEvaluationMetadata,
    validate_site_status_metadata,
)
from app.schemas.workflow import (
    WorkflowStepResponse,
    WorkflowStepUpdate,
    WorkflowStepsResponse,
)
from app.schemas.site_document import SiteDocumentResponse
from app.schemas.site_profile import (
    SiteProfileCreate,
    SiteProfileResponse,
    SiteProfileUpdate,
)
from app.schemas.study import StudyStatusSummary
from app.schemas.feasibility import (
    CustomQuestionCreate,
    CustomQuestionResponse,
    CustomQuestionUpdate,
    FeasibilityAnswerSubmit,
    FeasibilityAttachmentResponse,
    FeasibilityFormQuestion,
    FeasibilityFormResponse,
    FeasibilityFormSubmit,
    FeasibilityQuestion,
    FeasibilityQuestionnaireResponse,
    FeasibilityRequestCreate,
    FeasibilityRequestResponse,
    FeasibilityResponseDisplay,
    FeasibilityResponsesDisplay,
)
from app.schemas.agreement import (
    AgreementCommentCreate,
    AgreementCommentResponse,
    AgreementCreate,
    AgreementDocumentResponse,
    AgreementOtpSendRequest,
    AgreementOtpSignRequest,
    AgreementResponse,
    AgreementSignedDocumentResponse,
    AgreementSigningLinkSendRequest,
    AgreementStatusUpdate,
    DocumentSaveRequest,
    FieldMappingsUpdate,
    PlaceholderConfigUpdate,
    StudyTemplateCreate,
    StudyTemplateResponse,
)

__all__ = [
    # conversation
    "ConversationCreate", "ConversationResponse", "ConversationStateUpdate",
    "ConversationWithMessages", "MessageCreate", "MessageDecisionUpdate", "MessageResponse",
    "WebhookPayload", "WebSocketEvent", "WebSocketMessage",
    # ai
    "AICheckMessageIssue", "AICheckMessageRequest", "AICheckMessageResponse",
    "AIComposeReplyDrafts", "AIComposeReplyRequest", "AIComposeReplyResponse",
    "ResearchPaperSummary",
    # attachment
    "AttachmentResponse",
    # thread
    "CombineThreadsRequest", "CreateThreadFromConversationRequest",
    "ThreadAttachmentResponse", "ThreadCombinationSuggestion", "ThreadCreate",
    "ThreadMessageCreate", "ThreadMessageResponse", "ThreadParticipantCreate",
    "ThreadParticipantResponse", "ThreadResponse", "ThreadSimilarityAnalysis",
    "ThreadWithMessages",
    # user
    "ConversationAccessCreate", "ConversationAccessResponse", "GrantAccessRequest",
    "Token", "UpdateConversationAccessRequest", "UserCreate", "UserLogin",
    "UserResponse", "UserRoleAssignmentCreate", "UserRoleAssignmentResponse",
    "UserSignup",
    # user_profile
    "EventCreate", "EventResponse", "IISStudyCreate", "IISStudyResponse",
    "RDStudyCreate", "RDStudyResponse", "UserProfileCreate", "UserProfileResponse",
    # chat
    "ChatDocumentResponse", "ChatMessageCreate", "ChatMessageResponse",
    # task
    "TaskCreate", "TaskLinks", "TaskResponse", "TaskUpdate",
    # site_status
    "SECONDARY_STATUS_MODELS", "ActiveNotRecruitingMetadata", "ClosedMetadata",
    "CompletedMetadata", "CountryStatusSummary", "InitiatedNotRecruitingMetadata",
    "InitiatingMetadata", "RecruitingMetadata", "SiteStatusDetail",
    "SiteStatusHistoryEntry", "StartupMetadata", "UnderEvaluationMetadata",
    "validate_site_status_metadata",
    # workflow
    "WorkflowStepResponse", "WorkflowStepUpdate", "WorkflowStepsResponse",
    # site_document
    "SiteDocumentResponse",
    # site_profile
    "SiteProfileCreate", "SiteProfileResponse", "SiteProfileUpdate",
    # study
    "StudyStatusSummary",
    # feasibility
    "CustomQuestionCreate", "CustomQuestionResponse", "CustomQuestionUpdate",
    "FeasibilityAnswerSubmit", "FeasibilityAttachmentResponse",
    "FeasibilityFormQuestion", "FeasibilityFormResponse", "FeasibilityFormSubmit",
    "FeasibilityQuestion", "FeasibilityQuestionnaireResponse",
    "FeasibilityRequestCreate", "FeasibilityRequestResponse",
    "FeasibilityResponseDisplay", "FeasibilityResponsesDisplay",
    # agreement
    "AgreementCommentCreate", "AgreementCommentResponse", "AgreementCreate",
    "AgreementDocumentResponse", "AgreementOtpSendRequest", "AgreementOtpSignRequest",
    "AgreementResponse", "AgreementSignedDocumentResponse",
    "AgreementSigningLinkSendRequest", "AgreementStatusUpdate",
    "DocumentSaveRequest", "FieldMappingsUpdate", "PlaceholderConfigUpdate",
    "StudyTemplateCreate", "StudyTemplateResponse",
]
