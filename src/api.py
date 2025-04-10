import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from loguru import logger

from .accounts.accounts_loading import load_accounts
from .app_context import ApiSettings, AppContext, Application
from .background_tasks.background_manager import BackgroundTaskManager
from .db import MailDB
from .endpoints import (
    accounts,
    background_tasks,
    chats,
    drafts,
    emails,
    refresh,
    summaries,
)
from .imap.imap_client import IMAPClient, TestIMAPClient
from .testing import TEST_ACCOUNT, load_test_messages


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

    app.include_router(accounts.router)
    app.include_router(emails.router)
    app.include_router(chats.router)
    app.include_router(summaries.router)
    app.include_router(drafts.router)
    app.include_router(background_tasks.router)
    app.include_router(refresh.router)

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

    return Application(
        app=app,
        context=AppContext(
            accounts=state_accounts,
            dbs=state_dbs,
            background_manager=state_bg,
        ),
        settings=settings,
    )
