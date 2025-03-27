import os
from datetime import datetime, timedelta
from hashlib import sha1
from pathlib import Path
from typing import List, Optional, TypeVar

from loguru import logger
from pydantic import BaseModel, EmailStr
from result import Ok, Result
from sqlmodel import JSON, Column, Field, Session, SQLModel, create_engine, select

from .accounts_loading import AccountSettings
from .chats import EmailChat, generate_default_chat
from .message import MailMessage
from .utils import return_error_and_log

TABLE_TYPE = TypeVar("TABLE_TYPE", bound=SQLModel)


class EmailChatSQL(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email_message_id: str = Field(index=True, unique=True)
    chat_json: str
    authors: list[str] = Field(default_factory=list, sa_column=Column(JSON))


def sql_email_chat_to_email_chat(chat: EmailChatSQL) -> EmailChat:
    return EmailChat.model_validate_json(chat.chat_json)


class EmailSummarySQL(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email_message_id: str = Field(index=True, unique=True)
    summary_text: str


class ReplyDraftSQL(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email_message_id: str = Field(index=True, unique=True)
    draft_text: str


class UpdateStatus(BaseModel):
    last_update: datetime


class MailMessageSQL(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    mailbox: str
    content_file: str
    date_received: datetime
    date_sent: datetime
    deleted_status: bool = False
    junk_mail_status: bool = False
    message_id: str = Field(index=True, unique=True)
    reply_to: Optional[str]
    sender: EmailStr
    subject: Optional[str]
    was_replied_to: bool = False
    imap_uid: int


def sql_message_to_standard_message(mail: MailMessageSQL) -> MailMessage:
    content = Path(mail.content_file).read_text(encoding="utf-8")
    return MailMessage(
        Id=mail.imap_uid,
        Mailbox=mail.mailbox,
        Content=content,
        Date_Received=mail.date_received,
        Date_Sent=mail.date_sent,
        Deleted_Status=mail.deleted_status,
        Junk_Mail_Status=mail.junk_mail_status,
        Message_ID=mail.message_id,
        Reply_To=mail.reply_to,
        Sender=mail.sender,
        Subject=mail.subject,
        Was_Replied_To=mail.was_replied_to,
    )


class MailDB:
    def __init__(self, base_dir: str, settings: AccountSettings):
        self.settings = settings
        self.path = Path(base_dir) / settings.apple_mail_name
        self.path.mkdir(parents=True, exist_ok=True)

        self.contents_folder = self.path / "contents"
        self.contents_folder.mkdir(exist_ok=True)

        self.sql_folder = self.path / "sql"
        self.sql_folder.mkdir(exist_ok=True)
        self.db_path = self.sql_folder / "mail.db"
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
        content_sha = sha1(str(email_obj.Message_ID).encode()).hexdigest()
        content_file = self.contents_folder / content_sha

        if not content_file.exists():
            with open(content_file, "w", encoding="utf-8") as f:
                f.write(email_obj.Content)

        if (
            self.query_first_item(
                MailMessageSQL, MailMessageSQL.message_id == email_obj.Message_ID
            )
            is not None
        ):
            logger.warning(
                f"Email with Message_ID {email_obj.Message_ID} already saved."
            )
            return None

        self.add_value(
            MailMessageSQL(
                mailbox=email_obj.Mailbox,
                content_file=str(content_file),
                date_received=email_obj.Date_Received,
                date_sent=email_obj.Date_Sent,
                deleted_status=email_obj.Deleted_Status,
                junk_mail_status=email_obj.Junk_Mail_Status,
                message_id=email_obj.Message_ID,
                reply_to=email_obj.Reply_To,
                sender=email_obj.Sender,
                subject=email_obj.Subject,
                was_replied_to=email_obj.Was_Replied_To,
                imap_uid=email_obj.Id,
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
        return list(self.query_table(MailMessageSQL.message_id), where_clauses)

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
            raise return_error_and_log(f"Mail with Message_ID {email_id} not found.")

        if mail.Reply_To is None:
            return Ok(generate_default_chat(mail))

        with Session(self.engine) as session:
            statement = select(EmailChatSQL).where(
                EmailChatSQL.email_message_id == email_id
            )
            summary = session.exec(statement).first()

        if summary is None:
            return None

        return Ok(sql_email_chat_to_email_chat(summary))
