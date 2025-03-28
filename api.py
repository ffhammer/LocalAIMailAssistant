import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger
from pydantic_settings import BaseSettings
from sqlalchemy import select

from src.accounts_loading import AccountSettings, load_accounts
from src.background_manager import (
    JOB_TYPE,
    STATUS,
    BackgroundTaskManager,
    JobStatus,
    JobStatusSQL,
)
from src.chats import EmailChat, generate_default_chat
from src.imap_querying import IMAPClient, TestIMAPClient, list_mailboxes_of_account
from src.mail_db import (
    EmailChatSQL,
    EmailSummarySQL,
    MailDB,
    MailMessageSQL,
    UpdateStatus,
)
from src.message import MailMessage
from src.refresh import refresh_mailbox
from src.testing import TEST_ACCOUNT, load_test_messages


class ApiSettings(BaseSettings):
    TEST_BACKEND: str = "False"
    PATH_TO_TEST_DATA: str = "test_data/data.json"
    LOG_LEVEL: str = "DEBUG"
    TEST_DB_PATH: str = "test_db"
    DEFAULT_DB_DIR: str = "db"
    LOAD_TEST_DATA: bool = True


@dataclass
class AppContext:
    accounts: dict[str, AccountSettings]
    dbs: dict[str, MailDB]
    background_manager: BackgroundTaskManager


class Application:
    current: Optional["Application"] = None

    def __new__(cls, *args, **kwargs):
        cls.current = super().__new__(cls)
        return cls.current

    def __init__(self, app: FastAPI, context: AppContext, settings=ApiSettings):
        self.app: FastAPI = app
        self.context: AppContext = context
        self.settings: ApiSettings = settings

    @classmethod
    def get_current_context(cls) -> AppContext:
        if cls.current is None:
            raise ValueError("Application not instantiated")

        return cls.current.context


router = APIRouter()


@router.get("/accounts", response_model=List[dict])
def list_accounts():
    """
    Lists configured accounts.
    """
    context: AppContext = Application.get_current_context()

    return [
        {
            "account_id": key,
            "apple_mail_name": settings.apple_mail_name,
            "imap_server": settings.imap_server,
            "user": settings.user,
            "name": settings.user_for_mail,
        }
        for key, settings in context.accounts.items()
    ]


@router.get("/accounts/{account_id}/mailboxes", response_model=List[str])
def list_mailboxes(account_id: str):
    """
    Lists mailboxes for the specified account.
    """
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")
    return list_mailboxes_of_account(context.accounts[account_id])


@router.get(
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
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    if mailbox not in list_mailboxes_of_account(context.accounts[account_id]):
        raise HTTPException(status_code=404, detail="Mailbox not found")

    db = context.dbs[account_id]

    args = [MailMessageSQL.mailbox == mailbox]
    if from_date is not None:
        args.append(MailMessageSQL.date_sent > from_date)
    if to_date is not None:
        args.append(MailMessageSQL.date_sent < to_date)

    return db.query_emails(*args)


@router.get("/accounts/{account_id}/emails/{message_id}", response_model=MailMessage)
def get_email_details(
    account_id: str,
    message_id: str,
):
    """
    Retrieves full details of a single email by its message_id.
    Here, we assume a single account (the first one) for simplicity.
    """
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = context.dbs[account_id]
    email = db.get_email_by_message_id(message_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")
    return email


@router.get("/accounts/{account_id}/chats/{message_id}", response_model=EmailChat)
def get_email_chat(
    account_id: str,
    message_id: str,
):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    db = context.dbs[account_id]

    chat = db.get_mail_chat(email_id=message_id)

    if chat is not None:
        return chat

    email = db.get_email_by_message_id(message_id)
    if email is None:
        raise HTTPException(status_code=404, detail="Email not found")

    return generate_default_chat(email)


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


@router.post("/accounts/{account_id}/summaries/generate/{message_id}")
def generate_email_summary(account_id: str, message_id: str):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    if get_email_summary(account_id=account_id, message_id=message_id) is not None:
        return JSONResponse(content={"detail": "Summary already exists."})

    context.background_manager.add_job(
        job_type=JOB_TYPE.summary, email_message_id=message_id, account_id=account_id
    )
    return JSONResponse(content={"detail": "Summary generation job queued."})


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


@router.post("/accounts/{account_id}/chats/generate/{message_id}")
def generate_email_chat(account_id: str, message_id: str):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    if context.dbs[account_id].get_mail_chat(email_id=message_id) is not None:
        return JSONResponse(content={"detail": "Chat already exists."})

    context.background_manager.add_job(
        job_type=JOB_TYPE.chat, email_message_id=message_id, account_id=account_id
    )
    return JSONResponse(content={"detail": "Chat generation job queued."})


@router.post("/accounts/{account_id}/chats/generate")
def generate_email_chats(account_id: str):
    """Generate all open chats"""
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")

    missing_ids: List[str] = context.dbs[account_id].query_email_ids(
        MailMessageSQL.reply_to.is_not(None),
        ~MailMessageSQL.message_id.in_(select(EmailChatSQL.email_message_id)),
    )

    for msg_id in missing_ids:
        context.background_manager.add_job(
            job_type=JOB_TYPE.chat, email_message_id=msg_id, account_id=account_id
        )

    return JSONResponse(content={"detail": f"Queued {len(missing_ids)} chats."})


@router.get("/background/status", response_model=List[JobStatus])
def get_background_status(
    job_type: Optional[JOB_TYPE] = None,
    status: Optional[STATUS] = None,
    message_id: Optional[str] = None,
    account_id: Optional[str] = None,
):
    context: AppContext = Application.get_current_context()
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

    return context.background_manager.query_status(*args)


@router.get("/accounts/{account_id}/status/", response_model=Optional[UpdateStatus])
def get_last_update_status(account_id: str):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")
    db = context.dbs[account_id]
    return db.get_update_status()


@router.post(
    "/accounts/{account_id}/update",
    response_class=StreamingResponse,
    response_description="A stream of message_ids for each succesfully saved new mail",
)
async def post_update_account(
    account_id: str,
    mailbox: str,
    after_date: Optional[datetime] = None,
):
    context: AppContext = Application.get_current_context()
    if account_id not in context.dbs:
        raise HTTPException(status_code=404, detail="Account not found")
    if mailbox not in list_mailboxes_of_account(context.accounts[account_id]):
        raise HTTPException(status_code=404, detail="Mailbox not found")

    async def event_generator():
        async for message_id in refresh_mailbox(
            db=context.dbs[account_id], mailbox=mailbox, after_date=after_date
        ):
            logger.debug(f"yielding new message {message_id}")
            yield f"data: {message_id}\n\n"
            await asyncio.sleep(0.02)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def create_app(settings: Optional[ApiSettings] = None) -> Application:
    # Override settings if a test configuration is provided.
    if settings is None:
        settings = ApiSettings()
    settings: ApiSettings

    logger.level(settings.LOG_LEVEL)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        context: AppContext = Application.get_current_context()
        asyncio.create_task(context.background_manager.run())
        yield

    app = FastAPI(lifespan=lifespan, title="Local Email Summarization API")

    # Initialize our app context.
    if settings.TEST_BACKEND == "True":
        state_accounts = {"test": TEST_ACCOUNT}
        state_dbs = {
            "test": MailDB(base_dir=settings.TEST_DB_PATH, settings=TEST_ACCOUNT)
        }
        state_bg = BackgroundTaskManager(state_dbs, settings.TEST_DB_PATH)

        if settings.LOAD_TEST_DATA:
            messages_by_mailbox = load_test_messages(settings.PATH_TO_TEST_DATA)

            with IMAPClient(settings=TEST_ACCOUNT) as client:
                client: TestIMAPClient

                for mailbox, messages in messages_by_mailbox.items():
                    client.add_messages(messages, mailbox=mailbox)
    elif settings.TEST_BACKEND == "False":
        state_accounts = load_accounts("secrets/accounts.yaml")
        state_dbs = {
            account_id: MailDB(base_dir=settings.DEFAULT_DB_DIR, settings=settings)
            for account_id, settings in state_accounts.items()
        }
        state_bg = BackgroundTaskManager(state_dbs, settings.DEFAULT_DB_DIR)
    else:
        raise ValueError("TEST_BACKEND must be 'True' or 'False'")

    app.include_router(router)
    return Application(
        app=app,
        context=AppContext(
            accounts=state_accounts,
            dbs=state_dbs,
            background_manager=state_bg,
        ),
        settings=settings,
    )
