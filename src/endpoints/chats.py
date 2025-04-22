from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from result import is_err, is_ok
from sqlmodel import select

from ..app_context import AppContext, Application
from ..models import JOB_TYPE, EmailChat, EmailChatSQL, JobStatusSQL, MailMessage

router = APIRouter(tags=["Chats"])


@router.get("/accounts/{account_id}/chats/{message_id}", response_model=EmailChat)
def get_email_chat(
    account_id: str,
    message_id: str,
):
    context = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = context.dbs[account_id]

    chat = db.get_mail_chat(email_id=message_id)

    if is_err(chat):
        raise HTTPException(status_code=404, detail=chat.err())

    return chat.ok_value


@router.post(
    "/accounts/{account_id}/chats/generate/{message_id}",
    response_model=Optional[JobStatusSQL],
)
def generate_email_chat(account_id: str, message_id: str):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    if is_ok(context.dbs[account_id].get_mail_chat(email_id=message_id)):
        return None

    return context.background_manager.add_job(
        job_type=JOB_TYPE.chat, email_message_id=message_id, account_id=account_id
    )


@router.post("/accounts/{account_id}/chats/generate")
def generate_email_chats(account_id: str):
    """Generate all open chats"""
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    missing_ids: List[str] = context.dbs[account_id].query_email_ids(
        MailMessage.reply_to.is_not(None),
        ~MailMessage.message_id.in_(select(EmailChatSQL.email_message_id)),
    )

    for msg_id in missing_ids:
        context.background_manager.add_job(
            job_type=JOB_TYPE.chat,
            email_message_id=msg_id,
            account_id=account_id,
        )

    return JSONResponse(content={"detail": f"Queued {len(missing_ids)} chats."})
