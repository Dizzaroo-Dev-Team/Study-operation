"""Site workflow step schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class WorkflowStepResponse(BaseModel):
    step_name: str
    status: str
    step_data: Optional[Dict[str, Any]] = {}
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WorkflowStepsResponse(BaseModel):
    site_id: str
    steps: List[WorkflowStepResponse]


class WorkflowStepUpdate(BaseModel):
    status: Optional[str] = None
    step_data: Optional[Dict[str, Any]] = None
