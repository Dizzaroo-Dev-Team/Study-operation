"""Study-level summary schemas."""
from typing import Dict, List, Optional

from pydantic import BaseModel

from app.models import PrimarySiteStatus
from app.schemas.site_status import CountryStatusSummary


class StudyStatusSummary(BaseModel):
    study_id: str  # Study.study_id external identifier
    study_name: str
    study_status: Optional[PrimarySiteStatus] = None
    total_sites: int
    recruiting_sites: int
    status_counts: Dict[PrimarySiteStatus, int]
    countries: List[CountryStatusSummary]
