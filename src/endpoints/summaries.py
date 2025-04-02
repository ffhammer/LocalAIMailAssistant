from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sqlmodel import select

from ..app_context import AppContext, Application
from ..models import (
    JOB_TYPE,
    EmailSummarySQL,
    JobStatusSQL,
    MailMessageSQL,
)

router = APIRouter(tags=["Summaries"])


@router.get("/accounts/{account_id}/summaries/", response_model=List[str])
def get_email_summaries(
    account_id: str,
):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = context.dbs[account_id]
    return db.query_email_ids(
        MailMessageSQL.message_id.in_(select(EmailSummarySQL.email_message_id))
    )


@router.get(
    "/accounts/{account_id}/summaries/{message_id}", response_model=Optional[str]
)
def get_email_summary(
    account_id: str,
    message_id: str,
):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = context.dbs[account_id]
    return db.get_mail_summary(email_id=message_id)


@router.post(
    "/accounts/{account_id}/summaries/generate/{message_id}",
    response_model=Optional[JobStatusSQL],
)
def generate_email_summary(account_id: str, message_id: str):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    if get_email_summary(account_id=account_id, message_id=message_id) is not None:
        return None

    return context.background_manager.add_job(
        job_type=JOB_TYPE.summary, email_message_id=message_id, account_id=account_id
    )


@router.post("/accounts/{account_id}/summaries/generate")
def generate_email_summaries(account_id: str):
    """Generate all open summaries"""
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    missing_ids: List[str] = context.dbs[account_id].query_email_ids(
        ~MailMessageSQL.message_id.in_(select(EmailSummarySQL.email_message_id)),
    )

    for msg_id in missing_ids:
        context.background_manager.add_job(
            job_type=JOB_TYPE.summary, email_message_id=msg_id, account_id=account_id
        )

    return JSONResponse(content={"detail": f"Queued {len(missing_ids)} summaries."})
