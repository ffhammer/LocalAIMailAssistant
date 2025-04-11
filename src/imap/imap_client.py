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
from ..settings import ImapSettings, Settings
from .flags import MailFlag, parse_all_flags, parse_flags_filtered


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

    @abstractmethod
    def update_flags(self, mail: MailMessage):
        """update all the flags given the current state of the mail. raise if we dont get OK response"""


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

    def update_flags(self, mail: MailMessage):
        """
        Update the flags for a message in the test data storage.
        This directly modifies the stored MailMessage object.
        """
        stored_message = self.messages[mail.id]

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
                f"TestClient: Updated flags for UID {mail.id} to seen={mail.seen}, answered={mail.answered}, flagged={mail.flagged}"
            )


class RealIMAPClient(ImapClientInterface):
    def __init__(
        self,
        account: AccountSettings,
        settings: Settings,
    ):
        """
        Initialize the IMAPClient and establish a connection.

        :param imap_server: IMAP server address.
        :param user: Email username.
        :param password: Email password.
        :param input_port: IMAP server port (default 993 for SSL).
        """
        self.account = account
        self.settings: ImapSettings = settings.imap_settings
        self.conection = None  # IMAP connection object

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()

    def connect(self):
        """Connect to the IMAP server and authenticate."""
        try:
            logger.info("start login")
            self.conection = imaplib.IMAP4_SSL(
                self.account.imap_server, port=self.account.input_port, timeout=5
            )
            self.conection.login(self.account.user, self.account.password)
            logger.info("login finished")
        except imaplib.IMAP4.error as e:
            raise ConnectionError(
                f"Failed to connect or authenticate with the IMAP server: {e}"
            )

    def logout(self):
        """Log out from the IMAP server."""
        if self.conection:
            try:
                self.conection.logout()
            except Exception as e:
                logger.error(f"Error while logging out: {e}")

    def _select(self, mailbox: str, readonly: bool = False) -> None:
        status, _ = self.conection.select(mailbox=mailbox, readonly=readonly)
        if status != "OK":
            raise Exception(f"selecting mailbox {mailbox} failed")

    def _check_result_throw(self, result, msg="not received OK from imap") -> None:
        if result != "OK":
            logger.error(msg)
            raise imaplib.IMAP4.error(msg)

    def fetch_uids_after_date(
        self, mailbox: str = "INBOX", after_date: Optional[datetime] = None
    ) -> list[int]:
        if mailbox not in self.list_mailboxes():
            raise ValueError("mailbox is not found")
        if self.conection is None:
            raise PermissionError("You need to call the server as a context")
        self._select(mailbox, readonly=True)
        criteria = f"(SINCE {after_date.strftime('%d-%b-%Y')})" if after_date else "ALL"

        result, data = self.conection.uid("SEARCH", None, criteria)
        self._check_result_throw(result, "Failed to fetch UIDs")

        return [int(uid) for uid in data[0].split()]

    def fetch_email_by_uid(
        self, uid: int, mailbox: str = "INBOX"
    ) -> Optional[MailMessage]:
        if self.conection is None:
            raise PermissionError("You need to call the server as a context")
        self._select(mailbox)
        try:
            result, data = self.conection.uid("FETCH", str(uid), "(RFC822)")
            if result != "OK" or not data or not isinstance(data[0], tuple):
                return None
            msg = email.message_from_bytes(data[0][1], policy=default)
        except TimeoutError:
            logger.error(f"received timeout error for uid: '{uid}'")
            return None

        return parse_processed_email(msg, mailbox, uid)

    def list_mailboxes(self) -> list[str]:
        if self.conection is None:
            raise PermissionError("You need to call the server as a context")
        result, mailboxes = self.conection.list()
        self._check_result_throw(result, "Failed to list mailboxes")

        return [m.decode().split()[-1].strip('"') for m in mailboxes]

    def get_mailbox_quota(self, mailbox: str = "INBOX") -> Optional[tuple[int, int]]:
        if self.conection is None:
            raise PermissionError("You need to call the server as a context")
        try:
            result, data = self.conection.getquota(f'"{mailbox}"')
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
        self._select(mailbox=mailbox, readonly=True)
        typ, data = self.conection.search(None, "ALL")
        self._check_result_throw(typ, f"can't get {mailbox} numbers")

        msg_ids = data[0].split()
        msg_range = f"{msg_ids[0].decode()}:{msg_ids[-1].decode()}"
        typ, data = self.conection.fetch(msg_range, "(FLAGS)")
        self._check_result_throw("Failed to fetch flags")

        return parse_flags_filtered(data=data)

    def update_flags(self, mail: MailMessage):
        """
        Update the flags for a specific email UID on the IMAP server.
        Uses the STORE command with FLAGS to replace existing flags.
        Raises imaplib.IMAP4.error if the update fails.
        """
        if self.conection is None:
            raise ConnectionError("IMAP client is not connected.")

        # Select the mailbox (MUST NOT be readonly for STORE)
        logger.debug(
            f"Selecting mailbox '{mail.mailbox}' for flag update (UID: {mail.id})"
        )
        self._select(mailbox=mail.mailbox, readonly=False)

        typ, data = self.conection.uid("FETCH", str(mail.id), "(FLAGS)")
        self._check_result_throw(
            typ, f"can't fetch mail with uid {mail.id} in mailbox {mail.mailbox}"
        )

        val = parse_all_flags(data)
        if val is None:
            raise Exception(f"can't parse flags to update correctly from {data}")

        existing_flags = set(val[1])

        desired_flags = set()
        if mail.seen:
            desired_flags.add(r"\Seen")
        if mail.answered:
            desired_flags.add(r"\Answered")
        if mail.flagged:
            desired_flags.add(r"\Flagged")

        flags_to_add = desired_flags - existing_flags
        flags_to_remove = existing_flags - desired_flags

        # Remove unwanted flags
        if flags_to_remove:
            formatted_flags = f"({' '.join(flags_to_remove)})"
            logger.debug(
                f"Removing flags {formatted_flags} for UID {mail.id} in mailbox '{mail.mailbox}'"
            )
            store_status, response = self.conection.uid(
                "STORE", str(mail.id), "-FLAGS", formatted_flags
            )

            self._check_result_throw(
                store_status,
                f"Failed to remove flags for UID {mail.id}. Server response: {response}",
            )

        # Add desired flags
        if flags_to_add:
            formatted_flags = f"({' '.join(flags_to_add)})"
            logger.info(
                f"Adding flags {formatted_flags} for UID {mail.id} in mailbox '{mail.mailbox}'"
            )
            store_status, response = self.conection.uid(
                "STORE", str(mail.id), "+FLAGS", formatted_flags
            )
            self._check_result_throw(
                store_status,
                f"Failed to add flags for UID {mail.id}. Server response: {response}",
            )

        logger.debug(
            f"Successfully updated flags for UID {mail.id} to {desired_flags}."
        )


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
