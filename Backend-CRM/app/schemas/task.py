"""Task schemas (action items)."""
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

TaskMode = Literal["remote", "on-site"]


class TaskLinks(BaseModel):
    siteId: Optional[str] = None
    sponsorId: Optional[str] = None
    monitoringVisitId: Optional[str] = None
    monitoringReportId: Optional[str] = None
    conversationId: Optional[str] = None
    messageId: Optional[str] = None


class TaskCreate(BaseModel):
    # `title` is kept optional for backwards compatibility - existing callers
    # (e.g. ConversationDetail) still pass one. The new global Tasks page uses
    # `description` as the primary text and may leave title empty.
    title: Optional[str] = None
    description: Optional[str] = None
    status: str = "open"  # 'open' | 'in-progress' | 'done' | 'cancelled'
    assigneeId: Optional[str] = None
    assigneeName: Optional[str] = None
    requestedBy: Optional[str] = None
    assignedTo: Optional[str] = None
    sponsorId: Optional[str] = None
    sponsorName: Optional[str] = None
    role: Optional[str] = None
    taskMode: Optional[TaskMode] = None
    dueDate: Optional[date] = None
    closedDate: Optional[date] = None
    statusUpdate: Optional[str] = None
    createdByUserId: Optional[str] = None
    links: Optional[TaskLinks] = None
    # Legacy fields for backward compatibility
    siteId: Optional[str] = None
    monitoringVisitId: Optional[str] = None
    monitoringReportId: Optional[str] = None
    sourceConversationId: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assigneeId: Optional[str] = None
    assigneeName: Optional[str] = None
    requestedBy: Optional[str] = None
    assignedTo: Optional[str] = None
    sponsorId: Optional[str] = None
    sponsorName: Optional[str] = None
    role: Optional[str] = None
    taskMode: Optional[TaskMode] = None
    dueDate: Optional[date] = None
    closedDate: Optional[date] = None
    statusUpdate: Optional[str] = None
    links: Optional[TaskLinks] = None


class TaskResponse(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    status: str
    assigneeId: Optional[str] = None
    assigneeName: Optional[str] = None
    requestedBy: Optional[str] = None
    assignedTo: Optional[str] = None
    sponsorId: Optional[str] = None
    sponsorName: Optional[str] = None
    role: Optional[str] = None
    taskMode: Optional[TaskMode] = None
    dueDate: Optional[date] = None
    closedDate: Optional[date] = None
    statusUpdate: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime
    createdByUserId: Optional[str] = None
    links: Optional[TaskLinks] = None
    # Legacy fields
    siteId: Optional[str] = None
    monitoringVisitId: Optional[str] = None
    monitoringReportId: Optional[str] = None
    sourceConversationId: Optional[str] = None
