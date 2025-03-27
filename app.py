from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import List, Optional
import uvicorn
from loguru import logger

from src.accounts_loading import load_accounts
from src.mail_db import MailDB, MailMessageSQL, EmailSummarySQL, EmailChatSQL
from src.message import MailMessage
from src.chats import EmailChat, generate_default_chat
from src.imap_querying import list_mailboxes_of_account
from src.background_manager import (
    BackgroundTaskManager,
    JOB_TYPE,
    STATUS,
    JobStatus,
    JobStatusSQL,
)
from sqlalchemy import select
import asyncio

from contextlib import asynccontextmanager

# Load accounts from configuration (assumes a YAML file with multiple accounts)
accounts = load_accounts("secrets/accounts.yaml")
dbs = {account_id: MailDB("db", settings) for account_id, settings in accounts.items()}
background_manager = BackgroundTaskManager(dbs, "db")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    asyncio.create_task(background_manager.run())
    yield


app = FastAPI(lifespan=lifespan, title="Local Email Summarization API")


@app.get("/accounts", response_model=List[dict])
def list_accounts():
    """
    Lists configured accounts.
    """
    return [
        {
            "account_id": key,
            "apple_mail_name": settings.apple_mail_name,
            "imap_server": settings.imap_server,
            "user": settings.user,
            "name": settings.user_for_mail,
        }
        for key, settings in accounts.items()
    ]


@app.get("/accounts/{account_id}/mailboxes", response_model=List[str])
def list_mailboxes(account_id: str):
    """
    Lists mailboxes for the specified account.
    """
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")
    return list_mailboxes_of_account(accounts[account_id])


@app.get(
    "/accounts/{account_id}/mailboxes/{mailbox}/emails",
    response_model=List[MailMessage],
)
def list_emails(
    account_id: str,
    mailbox: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
):
    """
    Lists emails from a given mailbox. For each email, return metadata including
    message_id, subject, sender, date_sent, snippet, and flags indicating if summary,
    draft, and chat are available.
    """
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    if mailbox not in list_mailboxes_of_account(accounts[account_id]):
        raise HTTPException(status_code=404, detail="Mailbox not found")

    db = dbs[account_id]

    args = [MailMessageSQL.mailbox == mailbox]
    if from_date is not None:
        args.append(MailMessageSQL.date_sent > from_date)
    if to_date is not None:
        args.append(MailMessageSQL.date_sent < to_date)

    return db.query_emails(*args)


@app.get("/accounts/{account_id}/emails/{message_id}", response_model=MailMessage)
def get_email_details(
    account_id: str,
    message_id: str,
):
    """
    Retrieves full details of a single email by its message_id.
    Here, we assume a single account (the first one) for simplicity.
    """
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = dbs[account_id]
    email = db.get_email_by_message_id(message_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


@app.get("/accounts/{account_id}/chats/{message_id}", response_model=EmailChat)
def get_email_chat(
    account_id: str,
    message_id: str,
):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = dbs[account_id]

    chat = db.get_mail_chat(email_id=message_id)

    if chat is not None:
        return chat

    email = db.get_email_by_message_id(message_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    return generate_default_chat(email)


@app.get("/accounts/{account_id}/summaries/", response_model=List[str])
def get_email_summaries(
    account_id: str,
):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = dbs[account_id]
    return db.query_email_ids(
        MailMessageSQL.message_id.in_(select(EmailSummarySQL.email_message_id))
    )


@app.get("/accounts/{account_id}/summaries/{message_id}", response_model=Optional[str])
def get_email_summary(
    account_id: str,
    message_id: str,
):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = dbs[account_id]
    return db.get_mail_summary(email_id=message_id)


@app.post("/accounts/{account_id}/summaries/generate/{message_id}")
def generate_email_summary(account_id: str, message_id: str):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    if get_email_summary(account_id=account_id, message_id=message_id) is not None:
        return JSONResponse(content={"detail": "Summary already exists."})

    background_manager.add_job(
        job_type=JOB_TYPE.summary, email_message_id=message_id, account_id=account_id
    )
    return JSONResponse(content={"detail": "Summary generation job queued."})


@app.post("/accounts/{account_id}/summaries/generate")
def generate_email_summaries(account_id: str):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    missing_ids: List[str] = dbs[account_id].query_email_ids(
        ~MailMessageSQL.message_id.in_(select(EmailSummarySQL.email_message_id)),
    )

    for msg_id in missing_ids:
        background_manager.add_job(
            job_type=JOB_TYPE.summary, email_message_id=msg_id, account_id=account_id
        )

    return JSONResponse(content={"detail": f"Queued {len(missing_ids)} summaries."})


@app.post("/accounts/{account_id}/chats/generate/{message_id}")
def generate_email_chat(account_id: str, message_id: str):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    if dbs[account_id].get_mail_chat(email_id=message_id) is not None:
        return JSONResponse(content={"detail": "Chat already exists."})

    background_manager.add_job(
        job_type=JOB_TYPE.chat, email_message_id=message_id, account_id=account_id
    )
    return JSONResponse(content={"detail": "Chat generation job queued."})


@app.post("/accounts/{account_id}/chats/generate")
def generate_email_chats(account_id: str):
    if account_id not in dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    missing_ids: List[str] = dbs[account_id].query_email_ids(
        MailMessageSQL.reply_to.is_not(None),
        ~MailMessageSQL.message_id.in_(select(EmailChatSQL.email_message_id)),
    )

    for msg_id in missing_ids:
        background_manager.add_job(
            job_type=JOB_TYPE.chat, email_message_id=msg_id, account_id=account_id
        )

    return JSONResponse(content={"detail": f"Queued {len(missing_ids)} chats."})


@app.get("/background/status", response_model=List[JobStatus])
def get_background_status(
    job_type: Optional[JOB_TYPE] = None,
    status: Optional[STATUS] = None,
    message_id: Optional[str] = None,
    account_id: Optional[str] = None,
):
    args = []

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

    return background_manager.query_status(*args)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
