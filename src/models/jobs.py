from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel
from sqlmodel import Field, SQLModel


class JOB_TYPE(StrEnum):
    summary = "summary"
    draft = "draft"
    chat = "chat"


class STATUS(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class JobStatusSQL(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_type: str
    email_message_id: str = Field(index=True)
    account_id: str
    status: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    output: Optional[str] = None

    @classmethod
    def from_job_status(cls, status: "JobStatus") -> "JobStatusSQL":
        return cls(
            job_type=str(status.job_type),
            email_message_id=status.email_message_id,
            account_id=status.account_id,
            status=str(status.status),
            start_time=status.start_time,
            end_time=status.end_time,
            error_message=status.error_message,
            output=status.output,
        )


class JobStatus(BaseModel):
    job_type: JOB_TYPE
    email_message_id: str
    account_id: str
    status: STATUS
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error_message: Optional[str] = None
    output: Optional[str] = None

    @classmethod
    def from_sql_model(cls, status: "JobStatusSQL") -> "JobStatus":
        return cls(
            job_type=status.job_type,
            email_message_id=str(status.email_message_id),
            account_id=status.account_id,
            status=status.status,
            start_time=status.start_time,
            end_time=status.end_time,
            error_message=status.error_message,
            output=status.output,
        )
