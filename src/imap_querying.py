import imaplib
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from .accounts_loading import AccountSettings


class SimpleMailInformation(BaseModel):
    email_id: str
    sent_date: datetime


class IMAPClient:
    def __init__(self, settings : AccountSettings):
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
            self.mail = imaplib.IMAP4_SSL(self.settings.imap_server, port=self.settings.input_port)
            self.mail.login(self.settings.user, self.settings.password)
        except imaplib.IMAP4.error as e:
            raise ConnectionError(f"Failed to connect or authenticate with the IMAP server: {e}")

    def logout(self):
        """Log out from the IMAP server."""
        if self.mail:
            try:
                self.mail.logout()
            except Exception as e:
                print(f"Error while logging out: {e}")

    def __del__(self):
        """Ensure proper cleanup when the object is deleted."""
        self.logout()

    def fetch_emails_after_date(
        self, mailbox: str = "INBOX", after_date: Optional[datetime] = None, batch_size: int = 5
    ) -> list[SimpleMailInformation]:
        """
        Fetch emails after a certain date from the specified mailbox.

        :param mailbox: Mailbox name (e.g., "INBOX").
        :param after_date: Fetch emails received after this date.
        :param batch_size: Number of emails to fetch in a single batch.
        :return: List of SimpleMailInformation objects with email_id and sent_date.
        """
        if self.mail is None:
            return PermissionError("you need to call the server as an context")
        
        # Select the mailbox
        self.mail.select(mailbox)

        # Format the date for the SINCE filter
        since_filter = after_date.strftime('%d-%b-%Y') if after_date else None

        # Search for emails
        if since_filter:
            result, data = self.mail.search(None, f"SINCE {since_filter}")
        else:
            result, data = self.mail.search(None, "ALL")

        if result != "OK":
            raise Exception("Failed to fetch emails")

        email_ids = data[0].split()
        messages = []  # Store (Message-ID, Date) tuples

        # Fetch email headers in batches
        for i in range(0, len(email_ids), batch_size):
            batch = email_ids[i:i + batch_size]  # Get the current batch
            batch_str = ','.join(batch.decode('utf-8') for batch in batch)  # Convert to string
            result, msg_data = self.mail.fetch(batch_str, "(BODY[HEADER.FIELDS (MESSAGE-ID DATE)])")

            if result == "OK":
                for response in msg_data:
                    if isinstance(response, tuple):
                        # Extract and clean Message-ID and Date headers
                        headers = response[1].decode("utf-8")
                        message_id = None
                        date = None

                        for line in headers.splitlines():
                            if line.startswith("Message-ID:"):
                                message_id = line.replace("Message-ID:", "").strip().strip("<>")
                            elif line.startswith("Date:"):
                                date_str = line.replace("Date:", "").strip()
                                normalized_date_str = date_str.split(" (")[0]  # Remove any text after '('
                                # Parse using strptime
                                date = datetime.strptime(normalized_date_str, '%a, %d %b %Y %H:%M:%S %z')

                        if message_id and date:
                            messages.append(SimpleMailInformation(email_id=message_id, sent_date=date))

        return messages
