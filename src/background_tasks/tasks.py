from typing import List, Optional

from loguru import logger
from result import Ok, Result, is_err

from src.database.mail_db import (
    EmailChatSQL,
    EmailSummarySQL,
    MailDB,
)
from src.llms.chats import EmailChat, generate_email_chat_with_llm
from src.llms.drafts import EmailDraftSQL, generate_draft_with_llm
from src.llms.summary import generate_summary_with_llm
from src.models.message import MailMessage
from src.settings import Settings
from src.utils import LogLevel, return_error_and_log


def generate_and_save_chat(
    db: MailDB, email_message_id: str, settings: Settings
) -> Result[EmailChat, str]:
    # Retrieve the MailMessage from the database by message_id
    mail: Optional[MailMessage] = db.get_email_by_message_id(email_message_id)
    if mail is None:
        return return_error_and_log(
            f"Mail with message_id {email_message_id} not found."
        )

    try:
        logger.debug(
            f"Generating chat for email\n{'-' * 100}\n{mail.plain_text}\n{'-' * 100}"
        )
        chat: EmailChat = generate_email_chat_with_llm(mail, settings=settings)
        logger.debug(f"Chat generated:\n{chat.model_dump_json(indent=2)}")

        db.add_value(
            EmailChatSQL(
                email_message_id=email_message_id,
                chat_json=chat.model_dump_json(),
                authors=chat.authors,
            )
        )
        logger.info(f"Saved chat for message_id {email_message_id}.")
        return Ok(chat)
    except Exception as exc:
        logger.exception(
            f"Failed to generate summary for message_id {email_message_id}: {exc}"
        )
        return return_error_and_log(
            f"Failed to generate chat for message_id {email_message_id}: {exc}"
        )


def generate_and_save_summary(
    db: MailDB, email_message_id: str, settings: Settings
) -> Result[str, str]:
    # Check if a summary already exists for this email
    existing_summary: Optional[EmailSummarySQL] = db.query_first_item(
        EmailSummarySQL, EmailSummarySQL.email_message_id == email_message_id
    )

    if existing_summary:
        return return_error_and_log(
            f"Summary already exists for message_id {email_message_id}.",
            level=LogLevel.info,
        )

    chat_return = db.get_mail_chat(email_id=email_message_id)
    if is_err(chat_return):
        return chat_return

    chat: EmailChat = chat_return.ok()

    try:
        summary_text = generate_summary_with_llm(chat, settings=settings)
        logger.debug(
            f"Summary generated for {email_message_id}:\n{'-' * 100}\n{summary_text}\n{'-' * 100}"
        )
        db.add_value(
            EmailSummarySQL(
                email_message_id=email_message_id,
                summary_text=summary_text,
            )
        )

        logger.info(f"Saved summary for message_id {email_message_id}.")
        return Ok(summary_text)
    except Exception as exc:
        logger.exception(
            f"Failed to generate summary for message_id {email_message_id}: {exc}"
        )

        return return_error_and_log(
            f"Failed to generate summary for message_id {email_message_id}: {exc}"
        )


def generate_and_save_draft(
    db: MailDB, message_id: str, settings: Settings
) -> Result[EmailDraftSQL, str]:
    mail: Optional[MailMessage] = db.get_email_by_message_id(message_id)
    if mail is None:
        return return_error_and_log(f"Mail with message_id {message_id} not found.")

    draft_subjcet = mail.sender  # from how the message is

    existing_drafts: list[EmailDraftSQL] = db.query_table(
        EmailDraftSQL, EmailDraftSQL.message_id == message_id
    )
    version_number = 1
    if existing_drafts:
        existing_drafts.sort(key=lambda x: x.version_number)
        version_number = existing_drafts[-1].version_number + 1

    # we want other chats with the same subject  but different ids
    context_chats: List[EmailChatSQL] = db.query_table(
        EmailChatSQL,
        EmailChatSQL.email_message_id != message_id,
        EmailChatSQL.authors.contains([draft_subjcet]),
    )

    message_chat_res = db.get_mail_chat(message_id)
    if is_err(message_chat_res):
        return message_chat_res

    try:
        logger.debug(
            f"Generating draft {version_number} {message_id}, with {len(context_chats)} context chats and {existing_drafts} existing drafts"
        )

        res = generate_draft_with_llm(
            message_id=message_id,
            current_chat=message_chat_res.ok_value,
            context_chats=context_chats,
            previous_drafts=existing_drafts,
            current_version=version_number,
            settings=settings,
        )
        db.add_value(res)
        logger.debug(f"Succesfully generated draft {version_number} {message_id}")
        return Ok(res)
    except Exception as ecx:
        logger.exception("generate failed")
        return return_error_and_log(
            f"Generating draft {version_number} {message_id} failed with: {ecx}"
        )
