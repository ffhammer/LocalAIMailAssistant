import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List
from loguru import logger
from sqlalchemy import select
from sqlmodel import Session
from tqdm import tqdm

from src.mail_db import MailDB, MailMessageSQL, EmailChatSQL
from src.message import MailMessage
from src.chats import EmailChat, generate_email_chat_with_ollama


def format_email_chat(chat: EmailChat) -> str:
    return "\n\n".join(
        f"Author: {e.author}\nDate: {e.date_sent}\nContent:\n{e.enty_content}"
        for e in chat.entries
    )


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
                f"Generating chat for email\n{"-"*100}\n{mail.Content}\n{"-"*100}."
            )
            chat: EmailChat = generate_email_chat_with_ollama(mail)
            logger.debug(f"Chat generated:\n{format_email_chat(chat)}")

            with Session(self.engine) as session:
                chat_record = EmailChatSQL(
                    email_message_id=email_message_id, chat_json=chat.model_dump_json()
                )
                session.add(chat_record)
                session.commit()
                logger.info(f"Saved chat for Message_ID {email_message_id}.")
        except Exception as exc:
            logger.exception(
                f"Failed to generate chat for Message_ID {email_message_id}: {exc}"
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
