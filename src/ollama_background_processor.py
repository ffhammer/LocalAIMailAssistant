from sqlalchemy import select
from sqlmodel import Session
from tqdm import tqdm
from loguru import logger

from src.mail_db import MailDB, EmailChatSQL, EmailSummarySQL, MailMessageSQL
from src.message import MailMessage
from src.chats import EmailChat, generate_default_chat, generate_email_chat_with_ollama
from src.summary import generate_summary
from typing import Optional, List


class BackgroundOllamaProcessor:
    def __init__(self, db: MailDB):
        self.mail_db: MailDB = db
        self.engine = db.engine

    def generate_and_save_chat(self, email_message_id: str) -> None:
        # Retrieve the MailMessage from the database by message_id
        mail: Optional[MailMessage] = self.mail_db.get_email_by_message_id(
            email_message_id
        )
        if mail is None:
            logger.error(f"Mail with Message_ID {email_message_id} not found.")
            return

        try:
            logger.debug(
                f"Generating chat for email\n{'-'*100}\n{mail.Content}\n{'-'*100}"
            )
            chat: EmailChat = generate_email_chat_with_ollama(mail)
            logger.debug(f"Chat generated:\n{chat.model_dump_json(indent=2)}")

            with Session(self.engine) as session:
                chat_record = EmailChatSQL(
                    email_message_id=email_message_id,
                    chat_json=chat.model_dump_json(),
                )
                session.add(chat_record)
                session.commit()
                logger.info(f"Saved chat for Message_ID {email_message_id}.")
        except Exception as exc:
            logger.exception(
                f"Failed to generate chat for Message_ID {email_message_id}: {exc}"
            )

    def generate_and_save_summary(self, email_message_id: str) -> None:
        # Check if a summary already exists for this email
        with Session(self.engine) as session:
            existing_summary = session.exec(
                select(EmailSummarySQL).where(
                    EmailSummarySQL.email_message_id == email_message_id
                )
            ).first()
            if existing_summary:
                logger.info(
                    f"Summary already exists for Message_ID {email_message_id}."
                )
                return

        # Attempt to retrieve a chat for this email
        chat: Optional[EmailChat] = None
        with Session(self.engine) as session:
            chat_record = session.exec(
                select(EmailChatSQL).where(
                    EmailChatSQL.email_message_id == email_message_id
                )
            ).first()
            if chat_record:
                try:
                    chat = EmailChat.model_validate_json(chat_record[0].chat_json)
                except Exception as e:
                    logger.error(
                        f"Failed to parse chat JSON for Message_ID {email_message_id}: {e}"
                    )
                    return

        # If no chat exists, try to generate a default chat from the mail
        if chat is None:
            mail: Optional[MailMessage] = self.mail_db.get_email_by_message_id(
                email_message_id
            )
            if mail is None:
                logger.error(f"Mail with Message_ID {email_message_id} not found.")
                return
            chat = generate_default_chat(mail)

        try:
            summary_text = generate_summary(chat)
            logger.debug(
                f"Summary generated for {email_message_id}:\n{"-"*100}\n{summary_text}\n{"-"*100}"
            )

            with Session(self.engine) as session:
                summary_record = EmailSummarySQL(
                    email_message_id=email_message_id,
                    summary_text=summary_text,
                )
                session.add(summary_record)
                session.commit()
                logger.info(f"Saved summary for Message_ID {email_message_id}.")
        except Exception as exc:
            logger.exception(
                f"Failed to generate summary for Message_ID {email_message_id}: {exc}"
            )

    def generate_missing_chats(self) -> None:
        # Select all emails with a reply chain that do not yet have an associated chat
        with Session(self.engine) as session:
            stmt = select(MailMessageSQL.message_id).where(
                MailMessageSQL.reply_to.is_not(None),
                ~MailMessageSQL.message_id.in_(select(EmailChatSQL.email_message_id)),
            )
            missing_ids: List[str] = [i[0] for i in session.exec(stmt).all()]

        if missing_ids:
            logger.info(
                f"Generating chats for {len(missing_ids)} emails without an existing chat."
            )
        else:
            logger.info("No missing email chats found.")

        for msg_id in tqdm(missing_ids, desc="Generating email chats"):
            self.generate_and_save_chat(msg_id)

    def generate_missing_summaries(self) -> None:
        # Select all emails with a reply chain that do not have an associated summary
        with Session(self.engine) as session:
            stmt = select(MailMessageSQL.message_id).where(
                ~MailMessageSQL.message_id.in_(
                    select(EmailSummarySQL.email_message_id)
                ),
            )
            missing_ids: List[str] = [i[0] for i in session.exec(stmt).all()]

        if missing_ids:
            logger.info(
                f"Generating summaries for {len(missing_ids)} emails without an existing summary."
            )
        else:
            logger.info("No missing email summaries found.")

        for msg_id in tqdm(missing_ids, desc="Generating email summaries"):
            self.generate_and_save_summary(msg_id)
