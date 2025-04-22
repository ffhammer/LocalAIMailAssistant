import time
from datetime import datetime
from typing import Optional

from loguru import logger

from src.accounts.accounts_loading import AccountSettings
from src.imap.flags import MailFlag
from src.imap.ImapClientInterface import ImapClientInterface
from src.models.message import Attachment, MailMessage
from src.settings import ImapSettings, Settings


class TestIMAPClient(ImapClientInterface):
    instance: Optional["TestIMAPClient"] = None
    initialzed: bool = False

    def __new__(cls, *args, **kwargs):
        if cls.instance is None:
            cls.instance = super().__new__(cls)
            return cls.instance

        return cls.instance

    def __init__(
        self,
        account: AccountSettings,
        settings: Settings,
    ):
        self.account = account
        self.settings: ImapSettings = settings.imap_settings

        if self.initialzed:
            return
        self.messages: dict[int, MailMessage] = {}
        self.mailboxes: dict[str, list[int]] = {}

        self.mailboxes["INBOX"] = []

        self.initialzed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def add_messages(self, messages: list[MailMessage], mailbox: str = "INBOX") -> None:
        """
        Adds a list of MailMessage objects to the specified mailbox.
        Each MailMessage is assumed to have a unique Id.
        """
        if mailbox not in self.mailboxes:
            self.mailboxes[mailbox] = []
        for message in messages:
            uid = message.uid  # Assuming unique identifier is in Id
            self.messages[uid] = message
            self.mailboxes[mailbox].append(uid)

    def logout(self):
        # For the test client, there's no actual connection to close.
        pass

    def fetch_uids_after_date(
        self, mailbox: str = "INBOX", after_date: Optional[datetime] = None
    ) -> list[int]:
        if mailbox not in self.mailboxes:
            return []
        uids = []
        for uid in self.mailboxes[mailbox]:
            message = self.messages.get(uid)
            if message:
                # Compare Date_Sent (or Date_Received) with after_date if provided.
                if after_date is None or message.date_sent > after_date:
                    uids.append(uid)
        return sorted(uids, key=lambda x: self.messages.get(x).date_sent)

    def fetch_email_by_uid(
        self, uid: int, mailbox: str = "INBOX"
    ) -> Optional[tuple[MailMessage, list[Attachment]]]:
        time.sleep(0.1)

        if mailbox not in self.mailboxes or uid not in self.mailboxes[mailbox]:
            return None
        return self.messages.get(uid), []

    def list_mailboxes(self) -> list[str]:
        return list(self.mailboxes.keys())

    def fetch_all_flags_off_mailbox(
        self, mailbox: str = "INBOX"
    ) -> dict[int, tuple[MailFlag]]:
        vals = {}

        for id in self.mailboxes[mailbox]:
            flags = []
            mail = self.messages[id]
            if mail.seen:
                flags.append(MailFlag.Seen)
            if mail.answered:
                flags.append(MailFlag.Answered)
            if mail.flagged:
                flags.append(MailFlag.Flagged)

            vals[id] = tuple(flags)

        return vals

    def update_flags(self, mail: MailMessage):
        """
        Update the flags for a message in the test data storage.
        This directly modifies the stored MailMessage object.
        """
        stored_message = self.messages[mail.uid]

        # Update the stored message's flags
        updated = False
        if stored_message.seen != mail.seen:
            stored_message.seen = mail.seen
            updated = True
        if stored_message.answered != mail.answered:
            stored_message.answered = mail.answered
            updated = True
        if stored_message.flagged != mail.flagged:
            stored_message.flagged = mail.flagged
            updated = True

        if updated:
            logger.debug(
                f"TestClient: Updated flags for UID {mail.uid} to seen={mail.seen}, answered={mail.answered}, flagged={mail.flagged}"
            )
