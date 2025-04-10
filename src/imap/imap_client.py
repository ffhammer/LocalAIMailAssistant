import email
import imaplib
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime
from email.policy import default
from typing import Optional

from loguru import logger

from ..accounts.accounts_loading import AccountSettings
from ..models.message import MailMessage, parse_processed_email
from .flags import MailFlag, parse_flags


class ImapClientInterface(ABC):
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
    ) -> Optional[MailMessage]:
        pass

    @abstractmethod
    def list_mailboxes(self) -> list[str]:
        pass

    @abstractmethod
    def fetch_all_flags_off_mailbox(
        self, mailbox: str = "INBOX"
    ) -> dict[int, tuple[MailFlag]]:
        pass


class TestIMAPClient(ImapClientInterface):
    instance: Optional["TestIMAPClient"] = None
    initialzed: bool = False

    def __new__(cls, *args, **kwargs):
        if cls.instance is None:
            cls.instance = super().__new__(cls)
            return cls.instance

        return cls.instance

    def __init__(self, settings: AccountSettings):
        # Settings are not used for the test client

        if self.initialzed:
            return

        self.messages: dict[int, MailMessage] = {}  # uid -> MailMessage
        self.mailboxes: dict[str, list[int]] = {}  # mailbox name -> list of uids
        # Create a default mailbox
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
            uid = message.id  # Assuming unique identifier is in Id
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
    ) -> Optional[MailMessage]:
        time.sleep(0.1)

        if mailbox not in self.mailboxes or uid not in self.mailboxes[mailbox]:
            return None
        return self.messages.get(uid)

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


class RealIMAPClient(ImapClientInterface):
    def __init__(self, settings: AccountSettings):
        """
        Initialize the IMAPClient and establish a connection.

        :param imap_server: IMAP server address.
        :param user: Email username.
        :param password: Email password.
        :param input_port: IMAP server port (default 993 for SSL).
        """
        self.settings = settings
        self.mail = None  # IMAP connection object

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()

    def connect(self):
        """Connect to the IMAP server and authenticate."""
        try:
            logger.info("start login")
            self.mail = imaplib.IMAP4_SSL(
                self.settings.imap_server, port=self.settings.input_port, timeout=5
            )
            self.mail.login(self.settings.user, self.settings.password)
            logger.info("login finished")
        except imaplib.IMAP4.error as e:
            raise ConnectionError(
                f"Failed to connect or authenticate with the IMAP server: {e}"
            )

    def logout(self):
        """Log out from the IMAP server."""
        if self.mail:
            try:
                self.mail.logout()
            except Exception as e:
                logger.error(f"Error while logging out: {e}")

    def fetch_uids_after_date(
        self, mailbox: str = "INBOX", after_date: Optional[datetime] = None
    ) -> list[int]:
        if mailbox not in self.list_mailboxes():
            raise ValueError("mailbox is not found")
        if self.mail is None:
            raise PermissionError("You need to call the server as a context")
        self.mail.select(mailbox, readonly=True)
        criteria = f"(SINCE {after_date.strftime('%d-%b-%Y')})" if after_date else "ALL"
        result, data = self.mail.uid("SEARCH", None, criteria)
        if result != "OK":
            raise Exception("Failed to fetch UIDs")
        return [int(uid) for uid in data[0].split()]

    def fetch_email_by_uid(
        self, uid: int, mailbox: str = "INBOX"
    ) -> Optional[MailMessage]:
        if self.mail is None:
            raise PermissionError("You need to call the server as a context")
        self.mail.select(mailbox)
        try:
            result, data = self.mail.uid("FETCH", str(uid), "(RFC822)")
            if result != "OK" or not data or not isinstance(data[0], tuple):
                return None
            msg = email.message_from_bytes(data[0][1], policy=default)
        except TimeoutError:
            logger.error(f"received timeout error for uid: '{uid}'")

        return parse_processed_email(msg, mailbox, uid)

    def list_mailboxes(self) -> list[str]:
        if self.mail is None:
            raise PermissionError("You need to call the server as a context")
        result, mailboxes = self.mail.list()
        if result != "OK":
            raise Exception("Failed to list mailboxes")
        return [m.decode().split()[-1].strip('"') for m in mailboxes]

    def get_mailbox_quota(self, mailbox: str = "INBOX") -> Optional[tuple[int, int]]:
        if self.mail is None:
            raise PermissionError("You need to call the server as a context")
        try:
            result, data = self.mail.getquota(f'"{mailbox}"')
            if result != "OK" or not data:
                return None
            parts = data[0].decode().split()
            used = int(parts[-3])
            total = int(parts[-2])
            return total, used
        except Exception:
            logger.exception("get quota failed")
            return None

    def fetch_all_flags_off_mailbox(
        self, mailbox: str = "INBOX"
    ) -> dict[int, tuple[MailFlag]]:
        uids = self.fetch_uids_after_date(mailbox=mailbox)

        msg_range = f"{uids[0].decode()}:{uids[-1].decode()}"
        self.mail.select(mailbox=mailbox, readonly=True)
        typ, data = self.mail.mail.fetch(msg_range, "(FLAGS)")
        if typ != "OK":
            raise Exception("Failed to fetch flags")

        return parse_flags(data=data)


IMAPClient: ImapClientInterface = (
    TestIMAPClient if os.getenv("TEST_BACKEND", "False") == "True" else RealIMAPClient
)


def list_mailboxes_of_account(account: AccountSettings) -> Optional[list[str]]:
    try:
        with IMAPClient(settings=account) as client:
            return client.list_mailboxes()
    except Exception:
        logger.exception("list_mailboxes failed")
