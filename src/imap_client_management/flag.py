from loguru import logger
from result import Err, Result, is_err

from src.database.mail_db import MailDB, MailMessage
from src.imap import IMAPClient
from src.imap.ImapClientInterface import ImapClientInterface
from src.models import MailFlag


def toggle_flag(
    db: MailDB,
    email_message_id: str,
    flag: MailFlag,
) -> Result[MailMessage, str]:
    """Toggle a flag for an email message in the database and update it on the server."""
    # Toggle the flag in the database
    res = db.toggle_flag(email_message_id=email_message_id, flag=flag)
    if is_err(res):
        return res

    try:
        # Update the flag on the IMAP server
        with IMAPClient(account=db.account, settings=db.settings) as client:
            client: ImapClientInterface
            client.update_flags(mail=res.value)
    except Exception as e:
        logger.exception(
            f"Failed to update flags on server for {email_message_id}: {e}"
        )

        # Attempt to revert the flag change in the database
        revert_res = db.toggle_flag(email_message_id=email_message_id, flag=flag)
        if is_err(revert_res):
            logger.warning(
                f"Failed to revert flag change in database for {email_message_id} with flag {flag}"
            )

        return Err(
            "Failed to update flags on server and revert changes in the database."
        )

    return res
