import imaplib
from datetime import datetime
from typing import Optional
from .accounts_loading import AccountSettings
from loguru import logger
from tqdm import tqdm
import email
from email.policy import default


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


    def fetch_emails_after_date(
            self, mailbox: str = "INBOX", after_date: Optional[datetime] = None, batch_size: int = 5
        ) -> list[str]:
        """
        Fetch emails after a certain date from the specified mailbox.

        :param mailbox: Mailbox name (e.g., "INBOX").
        :param after_date: Fetch emails received after this date.
        :param batch_size: Number of emails to fetch in a single batch.
        :return: List of email Message-IDs.
        """
        if self.mail is None:
            return PermissionError("You need to call the server as a context")

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
        message_ids = []  # Store Message-IDs

        # Fetch email headers in batches
        for i in tqdm(range(0, len(email_ids), batch_size), desc = "Load New Messages from Imap server"):
            batch = email_ids[i:i + batch_size]  # Get the current batch
            batch_str = ','.join(batch.decode('utf-8') for batch in batch)  # Convert to string
            result, msg_data = self.mail.fetch(batch_str,'(BODY[HEADER.FIELDS (MESSAGE-ID)])')
            
            if len(batch) * 2!= len(msg_data):
                raise ValueError("expected twice as many responses as msg data")
            
            for msg_tuple in msg_data[::2]:
                # Ensure the response is a tuple
                if not isinstance(msg_tuple, tuple):
                    logger.warning(f"Unexpected response format: {msg_tuple}")
                    continue

                # Extract the raw email header data
                raw_email_data = msg_tuple[1]

                try:
                    # Parse the email using the modern email library
                    msg_obj = email.message_from_bytes(raw_email_data, policy=default)
                    message_id = msg_obj.get("Message-ID").strip().lstrip("<").rstrip(">")
                    
                    if message_id:
                        # Clean up the Message-ID if necessary
                        message_id = message_id.strip("<>")
                        message_ids.append(message_id)
                    else:
                        logger.warning("Message-ID not found in the email headers.")

                except Exception as e:
                    logger.error(f"Failed to parse message data: {e}")   
                    
        message_id_set = set(message_ids)
        if len(message_ids) != len(message_id_set):
            logger.warning("Imap returned duplicate messageIds")
        return list(message_id_set)

