"""Pydantic schemas for work log endpoints."""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, field_validator


class WorkLogCreate(BaseModel):
    job_id: Optional[str] = None
    contract_title: str
    upwork_contract_id: Optional[str] = None
    task_description: str
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    attachment_filename: Optional[str] = None
    attachment_text: Optional[str] = None
    notes: Optional[str] = None

    @field_validator('duration_minutes')
    @classmethod
    def positive_duration(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v <= 0:
            raise ValueError('duration_minutes must be positive')
        return v


class WorkLogUpdate(BaseModel):
    contract_title: Optional[str] = None
    task_description: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    attachment_filename: Optional[str] = None
    attachment_text: Optional[str] = None
    notes: Optional[str] = None


class WorkLogResponse(BaseModel):
    id: str
    user_id: str
    job_id: Optional[str]
    contract_title: str
    upwork_contract_id: Optional[str]
    task_description: str
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    duration_minutes: Optional[int]
    attachment_filename: Optional[str]
    attachment_text: Optional[str]
    notes: Optional[str]
    created_at: datetime
    model_config = {"from_attributes": True}


class WorkLogListResponse(BaseModel):
    logs: List[WorkLogResponse]
    total: int
    total_minutes: int


class ExtractImageRequest(BaseModel):
    image_base64: str          # data:image/... or raw base64
    filename: Optional[str] = None


class ExtractImageResponse(BaseModel):
    extracted_text: str
    summary: str
