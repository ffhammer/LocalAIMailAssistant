import os
from datetime import datetime, timedelta
from hashlib import sha1
from pathlib import Path
from typing import List, Optional, TypeVar

from loguru import logger
from result import Err, Ok, Result
from sqlmodel import Session, SQLModel, create_engine, select

from src.models import (
    EmailChat,
    EmailChatSQL,
    EmailDraftSQL,
    EmailSummarySQL,
    MailFlag,
    MailMessage,
    MailMessageSQL,
    UpdateStatus,
    sql_email_chat_to_email_chat,
    sql_message_to_standard_message,
)

from ..accounts.accounts_loading import AccountSettings
from ..llms.chats import generate_default_chat
from ..settings import Settings
from ..utils import LogLevel, return_error_and_log

EmailDraftSQL  # for create all
TABLE_TYPE = TypeVar("TABLE_TYPE", bound=SQLModel)


class MailDB:
    def __init__(self, base_dir: str, account: AccountSettings, settings: Settings):
        self.settings: Settings = settings
        self.account: AccountSettings = account

        self.path = Path(base_dir) / account.name
        self.path.mkdir(parents=True, exist_ok=True)

        self.contents_folder = self.path / "contents"
        self.contents_folder.mkdir(exist_ok=True)

        self.db_path = self.path / "mail.db"
        self.last_update_info = self.path / "update_info.json"
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        SQLModel.metadata.create_all(self.engine)

    def query_first_item(
        self, table: TABLE_TYPE, *where_clauses
    ) -> Optional[TABLE_TYPE]:
        with Session(self.engine) as session:
            statement = select(table)
            for clause in where_clauses:
                statement = statement.where(clause)

            return session.exec(statement=statement).first()

    def add_values(self, values: list[TABLE_TYPE]) -> None:
        with Session(self.engine) as session:
            session.add_all(values)
            session.commit()

    def add_value(self, value: TABLE_TYPE) -> None:
        with Session(self.engine) as session:
            session.add(value)
            session.commit()

    def query_table(self, table_model: SQLModel, *where_clauses) -> List[SQLModel]:
        with Session(self.engine) as session:
            statement = select(table_model)
            for clause in where_clauses:
                statement = statement.where(clause)
            results = session.exec(statement).all()
        return list(results)

    def get_update_status(self) -> Optional[UpdateStatus]:
        if not self.last_update_info.exists():
            return None

        try:
            return UpdateStatus.model_validate_json(self.last_update_info.read_text())
        except Exception as exc:
            logger.exception(f"Parsing update status failed with: {exc}")

    def write_update_status(self, status: UpdateStatus):
        try:
            with open(self.last_update_info, "w") as f:
                f.write(status.model_dump_json())
        except Exception as exc:
            logger.exception(f"Failed to save the status: {exc}")

    def save_email(self, email_obj: MailMessage):
        content_sha = sha1(str(email_obj.message_id).encode()).hexdigest()
        content_file = self.contents_folder / content_sha

        if not content_file.exists():
            with open(content_file, "w", encoding="utf-8") as f:
                f.write(email_obj.content)

        if (
            self.query_first_item(
                MailMessageSQL, MailMessageSQL.message_id == email_obj.message_id
            )
            is not None
        ):
            logger.warning(
                f"Email with Message_ID {email_obj.message_id} already saved."
            )
            return None

        self.add_value(
            MailMessageSQL(
                mailbox=email_obj.mailbox,
                content_file=str(content_file),
                date_received=email_obj.date_received,
                date_sent=email_obj.date_sent,
                deleted_status=email_obj.deleted_status,
                junk_mail_status=email_obj.junk_mail_status,
                message_id=email_obj.message_id,
                reply_to=email_obj.reply_to,
                sender=email_obj.sender,
                subject=email_obj.subject,
                was_replied_to=email_obj.was_replied_to,
                imap_uid=email_obj.id,
                seen=email_obj.seen,
                answered=email_obj.answered,
                flagged=email_obj.flagged,
            )
        )

    def get_email_by_message_id(self, email_id: str) -> Optional[MailMessage]:
        val = self.query_first_item(
            MailMessageSQL, MailMessageSQL.message_id == email_id
        )
        return None if val is None else sql_message_to_standard_message(val)

    def query_emails(self, *where_clauses) -> List[MailMessage]:
        mails = self.query_table(MailMessageSQL, *where_clauses)
        return [sql_message_to_standard_message(mail) for mail in mails]

    def query_email_ids(self, *where_clauses) -> List[str]:
        return list(self.query_table(MailMessageSQL.message_id, *where_clauses))

    def clean_old_emails(self, keep_days: int = 93) -> None:
        cutoff = datetime.now() - timedelta(days=keep_days)
        with Session(self.engine) as session:
            statement = select(MailMessageSQL).where(MailMessageSQL.date_sent < cutoff)
            old_emails = session.exec(statement).all()
            for email_obj in old_emails:
                content_path = Path(email_obj.content_file)
                try:
                    if content_path.exists():
                        os.remove(content_path)
                except Exception as e:
                    logger.error(f"Error deleting {content_path}: {e}")
                session.delete(email_obj)
            session.commit()

    def get_mail_summary(self, email_id: str) -> Optional[str]:
        summary: Optional[EmailSummarySQL] = self.query_first_item(
            EmailSummarySQL, EmailSummarySQL.email_message_id == email_id
        )

        return None if summary is None else summary.summary_text

    def get_mail_chat(self, email_id: str) -> Result[EmailChat, str]:
        mail: Optional[MailMessage] = self.get_email_by_message_id(email_id)
        if mail is None:
            return return_error_and_log(f"Mail with Message_ID {email_id} not found.")

        if mail.reply_to is None:
            return Ok(generate_default_chat(mail))

        with Session(self.engine) as session:
            statement = select(EmailChatSQL).where(
                EmailChatSQL.email_message_id == email_id
            )
            chat = session.exec(statement).first()

        if chat is None:
            return return_error_and_log(
                f"no chat for {email_id} saved", level=LogLevel.debug
            )

        return Ok(sql_email_chat_to_email_chat(chat))

    def delete_records(self, table_model: SQLModel, *where_clauses) -> None:
        with Session(self.engine) as session:
            stmt = select(table_model)
            for clause in where_clauses:
                stmt = stmt.where(clause)
            records = session.exec(stmt).all()
            for record in records:
                if hasattr(record, "content_file"):
                    content_path = Path(record.content_file)
                    if content_path.exists():
                        try:
                            os.remove(content_path)
                        except Exception as exc:
                            logger.error(f"Error deleting {content_path}: {exc}")
                session.delete(record)
            session.commit()

    def update_flags(self, data: dict[str, tuple[MailFlag]], mailbox) -> None:
        for uid, flags in data.items():
            mails: list[MailMessageSQL] = self.query_table(
                MailMessageSQL,
                MailMessageSQL.mailbox == mailbox,
                MailMessageSQL.imap_uid == uid,
            )

            if len(mails) == 0:
                logger.error(f"Can't find mail with uid {uid} in mailbox {mailbox}")
                continue
            elif len(mails) > 1:
                logger.warning(
                    f"Found multiple mails with uid {uid} in mailbox {mailbox}. Update all "
                )

            for mail in mails:
                mail.seen = MailFlag.Seen in flags
                mail.answered = MailFlag.Answered in flags
                mail.flagged = MailFlag.Flagged in flags

            with Session(self.engine) as session:
                for mail in mails:
                    session.add(mail)
                session.commit()

    def toggle_flag(
        self, email_message_id: str, flag: MailFlag
    ) -> Result[MailMessage, str]:
        mail: MailMessageSQL = self.query_first_item(
            MailMessageSQL, MailMessageSQL.message_id == email_message_id
        )

        if mail is None:
            return Err(f"can't find mail {email_message_id}")

        if flag == MailFlag.Answered:
            mail.answered = not mail.answered
        if flag == MailFlag.Seen:
            mail.seen = not mail.seen
        if flag == MailFlag.Flagged:
            mail.flagged = not mail.flagged

        with Session(self.engine) as session:
            session.add(mail)
            session.commit()

        return Ok(sql_email_chat_to_email_chat(mail))
