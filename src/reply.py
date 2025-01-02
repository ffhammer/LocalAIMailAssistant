from .accounts_loading import AccountSettings
from .data_formats import ProccesedMailMessage
from .apple_mail_io import load_reply_window_for_message
from loguru import logger
from datetime import datetime

def format_reply_content_inline(original_content: str, sender: str, date_received: datetime) -> str:
    """
    Formats the reply content by appending the original email content inline.
    """
    # Format the header line
    formatted_date = date_received.strftime("%d. %b %Y, at %H:%M")
    header = f"On {formatted_date}, {sender} wrote:\n"
    
    # Add the original content
    return f"{header}\n{original_content}"


def start_replying_to_mail(mail: ProccesedMailMessage, reply: str, settings: AccountSettings) -> bool:
    """
    Starts replying to a mail, formatting the old content inline with the reply.
    """
    try:
        # Format the reply with the original content inline
        formatted_content = format_reply_content_inline(
            original_content=mail.Content,
            sender=mail.Sender,
            date_received=mail.Date_Received
        )
        reply_content = f"{reply}\n\n{formatted_content}"
        
        # Open reply window
        load_reply_window_for_message(
            mail.Id,
            reply_content,
            account=settings.apple_mail_name,
            mailbox=settings.apple_mail_inbox_folder
        )
        return True
    except RuntimeError as e:
        # Log the error or handle it appropriately
        logger.error(f"Failed to open reply window for mail {mail.Id}: {e}")
        return False
