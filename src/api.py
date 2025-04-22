import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from loguru import logger

from .accounts.accounts_loading import load_accounts
from .app_context import AppContext, Application
from .background_tasks.background_manager import BackgroundTaskManager
from .database import MailDB
from .endpoints import (
    accounts,
    background_tasks,
    chats,
    drafts,
    emails,
    refresh,
    summaries,
)
from .imap import IMAPClient
from .imap.TestIMAPClient import TestIMAPClient
from .settings import Settings
from .testing import TEST_ACCOUNT, load_test_messages


def create_app(settings: Optional[Settings] = None) -> Application:
    # Override settings if a test configuration is provided.
    if settings is None:
        settings = Settings()
    settings: Settings

    logger.remove()
    logger.add(sys.stdout, level=settings.LOG_LEVEL)
    if settings.log_path is not None:
        logger.add(settings.log_path, level=settings.LOG_LEVEL)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        context: AppContext = Application.get_current_context()
        background_task = asyncio.create_task(context.background_manager.run())
        context.background_task = background_task
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
            "test": MailDB(
                base_dir=settings.TEST_DB_PATH, account=TEST_ACCOUNT, settings=settings
            )
        }
        state_bg = BackgroundTaskManager(
            state_dbs, settings=settings, base_dir=settings.TEST_DB_PATH
        )

        if settings.LOAD_TEST_DATA:
            messages_by_mailbox = load_test_messages(settings.PATH_TO_TEST_DATA)

            with IMAPClient(account=TEST_ACCOUNT, settings=settings) as client:
                client: TestIMAPClient

                for mailbox, messages in messages_by_mailbox.items():
                    client.add_messages(messages, mailbox=mailbox)
    elif settings.TEST_BACKEND == "False":
        state_accounts = load_accounts("secrets/accounts.yaml")
        state_dbs = {
            account_id: MailDB(
                base_dir=settings.DEFAULT_DB_DIR,
                account=account_setting,
                settings=settings,
            )
            for account_id, account_setting in state_accounts.items()
        }
        state_bg = BackgroundTaskManager(
            state_dbs, settings=settings, base_dir=settings.DEFAULT_DB_DIR
        )
    else:
        raise ValueError("TEST_BACKEND must be 'True' or 'False'")

    return Application(
        app=app,
        context=AppContext(
            accounts=state_accounts,
            dbs=state_dbs,
            background_manager=state_bg,
            settings=settings,
        ),
        settings=settings,
    )
