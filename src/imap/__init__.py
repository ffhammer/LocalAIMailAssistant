import os
from typing import Optional

from loguru import logger

from src.accounts.accounts_loading import AccountSettings
from src.settings import Settings

from .ImapClientInterface import ImapClientInterface
from .RealIMAPClient import RealIMAPClient
from .TestIMAPClient import TestIMAPClient

IMAPClient: ImapClientInterface = (
    TestIMAPClient if os.getenv("TEST_BACKEND", "False") == "True" else RealIMAPClient
)


def list_mailboxes_of_account(
    account: AccountSettings, settings: Settings
) -> Optional[list[str]]:
    try:
        with IMAPClient(account=account, settings=settings) as client:
            return client.list_mailboxes()
    except Exception:
        logger.exception("list_mailboxes failed")


__all__ = [
    "RealIMAPClient",
    "ImapClientInterface",
    "TestIMAPClient",
    "list_mailboxes_of_account",
    "IMAPClient",
]
