from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class AlertGenerationRequest(BaseModel):
    analysis_date: date
    baseline_days: int = Field(default=28, ge=14, le=60)
    region_code: str | None = None
    condition_code: str | None = None


class AlertDecisionRequest(BaseModel):
    status: Literal["approved", "dismissed"]
    reviewer_name: str = Field(min_length=2, max_length=120)
    note: str | None = Field(default=None, max_length=500)
