from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from src.accounts.accounts_loading import AccountSettings
from src.imap.flags import MailFlag
from src.models.message import Attachment, MailMessage
from src.settings import Settings


class ImapClientInterface(ABC):
    @abstractmethod
    def __init__(
        self,
        account: AccountSettings,
        settings: Settings,
    ):
        super().__init__()

    @abstractmethod
    def __enter__(self):
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @abstractmethod
    def logout(self):
        """Log out from the IMAP server."""
        pass

    @abstractmethod
    def fetch_uids_after_date(
        self, mailbox: str = "INBOX", after_date: Optional[datetime] = None
    ) -> list[int]:
        pass

    @abstractmethod
    def fetch_email_by_uid(
        self, uid: int, mailbox: str = "INBOX"
    ) -> Optional[tuple[MailMessage, list[Attachment]]]:
        pass

    @abstractmethod
    def list_mailboxes(self) -> list[str]:
        pass

    @abstractmethod
    def fetch_all_flags_off_mailbox(
        self, mailbox: str = "INBOX"
    ) -> dict[int, tuple[MailFlag]]:
        pass

    @abstractmethod
    def update_flags(self, mail: MailMessage):
        """update all the flags given the current state of the mail. raise if we dont get OK response"""
