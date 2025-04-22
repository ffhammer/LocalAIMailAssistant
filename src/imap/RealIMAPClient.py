import email
import imaplib
import time
from datetime import datetime
from email.policy import default
from typing import Optional

from loguru import logger

from src.accounts.accounts_loading import AccountSettings
from src.imap.ImapClientInterface import ImapClientInterface
from src.models.message import Attachment, MailMessage
from src.settings import ImapSettings, Settings

from .flags import MailFlag, parse_all_flags, parse_flags_filtered
from .parse_mails import parse_message


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
        self.connection = None  # IMAP connection object

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logout()

    def connect(self):
        """Connect to the IMAP server and authenticate."""
        try:
            logger.info("start login")
            self.connection = imaplib.IMAP4_SSL(
                self.account.imap_server, port=self.account.input_port, timeout=5
            )
            self.connection.login(self.account.user, self.account.password)
            logger.info("login finished")
        except imaplib.IMAP4.error as e:
            raise ConnectionError(
                f"Failed to connect or authenticate with the IMAP server: {e}"
            )

    def logout(self):
        """Log out from the IMAP server."""
        if self.connection:
            try:
                self.connection.logout()
            except Exception as e:
                logger.error(f"Error while logging out: {e}")

    def _retry(self, func, *args, **kwargs):
        attempts = self.settings.max_retries
        while attempts > 0:
            try:
                return func(*args, **kwargs)
            except (imaplib.IMAP4.error, Exception) as e:
                logger.error(f"Error: {e}. Reconnecting...")
                self.logout()
                time.sleep(self.settings.retry_delay)
                self.connect()
                attempts -= 1
        raise Exception("Max retry attempts reached.")

    def _select(self, mailbox: str, readonly: bool = False) -> None:
        def _select_mailbox():
            return self.connection.select(mailbox=mailbox, readonly=readonly)

        status, _ = self._retry(_select_mailbox)
        self._raise_on_status(status, f"selecting mailbox {mailbox} failed")

    def _raise_on_status(self, result, msg="not received OK from imap") -> None:
        if result != "OK":
            logger.error(f"{msg} - received: {result}")
            raise imaplib.IMAP4.error(msg)

    def fetch_uids_after_date(
        self, mailbox: str = "INBOX", after_date: Optional[datetime] = None
    ) -> list[int]:
        if mailbox not in self.list_mailboxes():
            raise ValueError("mailbox is not found")
        if self.connection is None:
            raise PermissionError("You need to call the server as a context")
        self._select(mailbox, readonly=True)
        criteria = f"(SINCE {after_date.strftime('%d-%b-%Y')})" if after_date else "ALL"

        def _fetch_uids():
            return self.connection.uid("SEARCH", None, criteria)

        result, data = self._retry(_fetch_uids)
        self._raise_on_status(result, "Failed to fetch UIDs")
        return [int(uid) for uid in data[0].split()]

    def fetch_email_by_uid(
        self, uid: int, mailbox: str
    ) -> Optional[tuple[MailMessage, list[Attachment]]]:
        if self.connection is None:
            raise PermissionError("You need to call the server as a context")
        self._select(mailbox)

        def _fetch_by_uid():
            return self.connection.uid("FETCH", str(uid), "(RFC822)")

        result, data = self._retry(_fetch_by_uid)
        if result != "OK" or not data or not isinstance(data[0], tuple):
            return None
        msg = email.message_from_bytes(data[0][1], policy=default)

        return parse_message(msg, mailbox, uid)

    def list_mailboxes(self) -> list[str]:
        def _list_collections():
            return self.connection.list()

        result, mailboxes = self._retry(_list_collections)
        self._raise_on_status(result, "Failed to list mailboxes")
        return [m.decode().split()[-1].strip('"') for m in mailboxes]

    def get_mailbox_quota(self, mailbox: str = "INBOX") -> Optional[tuple[int, int]]:
        def _get_quota():
            return self.connection.getquota(f'"{mailbox}"')

        result, data = self._retry(_get_quota)

        if result != "OK" or not data:
            return None
        parts = data[0].decode().split()
        used = int(parts[-3])
        total = int(parts[-2])
        return total, used

    def fetch_all_flags_off_mailbox(
        self, mailbox: str = "INBOX"
    ) -> dict[int, tuple[MailFlag]]:
        self._select(mailbox=mailbox, readonly=True)

        def __fetch_all():
            return self.connection.search(None, "ALL")

        typ, data = self._retry(__fetch_all)
        self._raise_on_status(typ, f"can't get {mailbox} numbers")

        msg_ids = data[0].split()
        msg_range = f"{msg_ids[0].decode()}:{msg_ids[-1].decode()}"

        def __fetch_flags():
            return self.connection.fetch(msg_range, "(FLAGS)")

        typ, data = self._retry(__fetch_flags)
        self._raise_on_status(typ, "Failed to fetch flags")
        return parse_flags_filtered(data=data)

    def _get_existing_flags(self, mail: MailMessage) -> set[MailFlag]:
        def _fetch_uids():
            return self.connection.uid("FETCH", str(mail.uid), "(FLAGS)")

        typ, data = self._retry(_fetch_uids)
        self._raise_on_status(
            typ, f"can't fetch mail with uid {mail.uid} in mailbox {mail.mailbox}"
        )

        val = parse_all_flags(data)
        if val is None:
            raise Exception(f"can't parse flags to update correctly from {data}")

        return set(val[1])

    def _remove_flags(self, mail: MailMessage, flags_to_remove: set[MailFlag]) -> None:
        if not flags_to_remove:
            return

        formatted_flags = f"({' '.join(flags_to_remove)})"
        logger.debug(
            f"Removing flags {formatted_flags} for UID {mail.uid} in mailbox '{mail.mailbox}'"
        )

        def _minus_flags():
            return self.connection.uid(
                "STORE", str(mail.uid), "-FLAGS", formatted_flags
            )

        store_status, response = self._retry(_minus_flags)

        self._raise_on_status(
            store_status,
            f"Failed to remove flags for UID {mail.uid}. Server response: {response}",
        )

    def _add_flags(self, mail: MailMessage, flags_to_add: set[MailFlag]) -> None:
        if not flags_to_add:
            return

        formatted_flags = f"({' '.join(flags_to_add)})"
        logger.info(
            f"Adding flags {formatted_flags} for UID {mail.uid} in mailbox '{mail.mailbox}'"
        )

        def _add_flags():
            return self.connection.uid(
                "STORE", str(mail.uid), "+FLAGS", formatted_flags
            )

        store_status, response = self._retry(_add_flags)
        self._raise_on_status(
            store_status,
            f"Failed to add flags for UID {mail.uid}. Server response: {response}",
        )

    def update_flags(self, mail: MailMessage):
        """
        Update the flags for a specific email UID on the IMAP server.
        Uses the STORE command with FLAGS to replace existing flags.
        Raises imaplib.IMAP4.error if the update fails.
        """
        # Select the mailbox (MUST NOT be readonly for STORE)
        logger.debug(
            f"Selecting mailbox '{mail.mailbox}' for flag update (UID: {mail.uid})"
        )
        self._select(mailbox=mail.mailbox, readonly=False)

        existing_flags = self._get_existing_flags(mail=mail)

        desired_flags = set()
        if mail.seen:
            desired_flags.add(r"\Seen")
        if mail.answered:
            desired_flags.add(r"\Answered")
        if mail.flagged:
            desired_flags.add(r"\Flagged")

        flags_to_add = desired_flags - existing_flags
        flags_to_remove = existing_flags - desired_flags

        self._remove_flags(mail=mail, flags_to_remove=flags_to_remove)
        self._add_flags(mail=mail, flags_to_add=flags_to_add)

        logger.debug(
            f"Successfully updated flags for UID {mail.uid} to {desired_flags}."
        )
