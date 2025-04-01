from typing import Optional

from fastapi import APIRouter, HTTPException

from ..app_context import AppContext, Application
from ..models import (
    JOB_TYPE,
    EmailDraftSQL,
    JobStatusSQL,
)

router = APIRouter()


@router.post(
    "/accounts/{account_id}/drafts/save/{message_id}",
)
def generate_save_draft(account_id: str, new_user_draft: EmailDraftSQL) -> bool:
    """Saves a new draft from the user.
    Swagger UI does not display the second argument:
    new_user_draft : EmailDraftSQL
    """

    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")
    db = context.dbs[account_id]
    db.add_value(new_user_draft)
    return True


@router.post(
    "/accounts/{account_id}/drafts/generate/{message_id}",
    response_model=Optional[JobStatusSQL],
)
def generate_email_draft(
    account_id: str,
    message_id: str,
):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = context.dbs[account_id]
    drafts: list[EmailDraftSQL] = db.query_table(
        EmailDraftSQL, EmailDraftSQL.message_id == message_id
    )
    drafts.sort(key=lambda x: x.version_number)

    last_draft_by_user = drafts[-1].by_user if len(drafts) else False

    if (
        not last_draft_by_user
        and get_latest_email_draft(account_id=account_id, message_id=message_id)
        is not None
    ):
        return None

    return context.background_manager.add_job(
        job_type=JOB_TYPE.draft, account_id=account_id, email_message_id=message_id
    )


@router.get(
    "/accounts/{account_id}/drafts/{message_id}",
    response_model=Optional[EmailDraftSQL],
)
def get_latest_email_draft(
    account_id: str,
    message_id: str,
):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = context.dbs[account_id]

    drafts: list[EmailDraftSQL] = db.query_table(
        EmailDraftSQL, EmailDraftSQL.message_id == message_id
    )

    if len(drafts) == 0:
        return None
    drafts.sort(key=lambda x: x.version_number)

    return drafts[-1]
