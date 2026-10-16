from datetime import date, time
from typing import Literal

from pydantic import BaseModel, Field


class AlertGenerationRequest(BaseModel):
    analysis_date: date
    baseline_days: int = Field(default=28, ge=14, le=60)
    hospital_code: str | None = None
    condition_code: str | None = None


class AlertDecisionRequest(BaseModel):
    status: Literal["approved", "dismissed"]
    reviewer_name: str = Field(min_length=2, max_length=120)
    note: str | None = Field(default=None, max_length=500)


class ActionUpdateRequest(BaseModel):
    status: Literal["pending", "in_progress", "completed", "cancelled"]
    assignee_name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=500)


class EmailAlertConfigRequest(BaseModel):
    enabled: bool
    schedule_time: time
    timezone: str = Field(min_length=1, max_length=80)
    recipients: list[str] = Field(default_factory=list, max_length=50)
    cc: list[str] = Field(default_factory=list, max_length=50)
    minimum_level: Literal["investigate", "escalate"] = "investigate"
    incident_master_email: str = Field(min_length=3, max_length=320)
    owner_emails: dict[str, str] = Field(default_factory=dict)


class EmailAlertSendRequest(BaseModel):
    analysis_date: date | None = None


class PredictiveAssessmentRequest(BaseModel):
    analysis_date: date
    hospital_code: str = Field(pattern=r"^[a-z0-9_]+$", max_length=80)
    condition_code: Literal["ili", "age", "dengue"]


class FollowupCompletionRequest(BaseModel):
    note: str = Field(min_length=3, max_length=500)
