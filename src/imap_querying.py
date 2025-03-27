import imaplib
from datetime import datetime
from typing import Optional
from .accounts_loading import AccountSettings
from loguru import logger
from tqdm import tqdm
import email
from email.policy import default
from .message import MailMessage, parse_processed_email


class IMAPClient:
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
        self.mail.select(mailbox)
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
        except TimeoutError:
            logger.error(f"received timeout error for uid: '{uid}'")

        if result != "OK" or not data or not isinstance(data[0], tuple):
            return None
        msg = email.message_from_bytes(data[0][1], policy=default)
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


def list_mailboxes_of_account(account: AccountSettings) -> Optional[list[str]]:

    try:
        with IMAPClient(settings=account) as client:
            return client.list_mailboxes()
    except Exception:
        logger.exception("list_mailboxes failed")
