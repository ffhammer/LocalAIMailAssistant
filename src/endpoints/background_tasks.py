from typing import List, Optional

from fastapi import APIRouter, HTTPException

from src.app_context import AppContext, Application
from src.models import (
    JOB_TYPE,
    STATUS,
    JobStatus,
    JobStatusSQL,
)

router = APIRouter(tags=["Background"])


@router.get("/background/status", response_model=List[JobStatus])
def get_background_status(
    job_id: Optional[int] = None,
    job_type: Optional[JOB_TYPE] = None,
    status: Optional[STATUS] = None,
    message_id: Optional[str] = None,
    account_id: Optional[str] = None,
):
    context: AppContext = Application.get_current_context()
    args = []

    if job_id is not None:
        args.append(JobStatusSQL.id == job_id)
    if job_type is not None:
        args.append(JobStatusSQL.job_type == job_type)
    if status is not None:
        args.append(JobStatusSQL.status == status)
    if message_id is not None:
        args.append(JobStatusSQL.email_message_id == message_id)
    if account_id is not None:
        args.append(JobStatusSQL.account_id == account_id)

    if not args:
        raise HTTPException(
            status_code=400, detail="At least one filter must be provided."
        )

    return context.background_manager.query_status(*args)
