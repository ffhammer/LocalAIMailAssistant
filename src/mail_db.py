import os
from pathlib import Path
from datetime import datetime, timedelta
from hashlib import sha1
from typing import Optional, List

from pydantic import EmailStr
from sqlmodel import Field, SQLModel, create_engine, Session, select
from loguru import logger
from .message import MailMessage
from .accounts_loading import AccountSettings
from .chats import EmailChat


class EmailChatSQL(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email_message_id: str = Field(index=True, unique=True)
    chat_json: str  # stored as JSON blob


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
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        SQLModel.metadata.create_all(self.engine)

    def save_email(self, email_obj: MailMessage) -> Optional[MailMessageSQL]:
        content_sha = sha1(str(email_obj.Message_ID).encode()).hexdigest()
        content_file = self.contents_folder / content_sha

        if not content_file.exists():
            with open(content_file, "w", encoding="utf-8") as f:
                f.write(email_obj.Content)

        with Session(self.engine) as session:
            existing = session.exec(
                select(MailMessageSQL).where(
                    MailMessageSQL.message_id == email_obj.Message_ID
                )
            ).first()
            if existing:
                logger.warning(
                    f"Email with Message_ID {email_obj.Message_ID} already saved."
                )
                return None

            orm_obj = MailMessageSQL(
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
            session.add(orm_obj)
            session.commit()
            session.refresh(orm_obj)
        return orm_obj

    def get_email_by_message_id(self, email_id: str) -> Optional[MailMessage]:
        with Session(self.engine) as session:
            statement = select(MailMessageSQL).where(
                MailMessageSQL.message_id == email_id
            )
            val = session.exec(statement).first()
        return None if val is None else sql_message_to_standard_message(val)

    def query_emails(self, *where_clauses) -> List[MailMessage]:
        with Session(self.engine) as session:
            statement = select(MailMessageSQL)
            for clause in where_clauses:
                statement = statement.where(clause)
            mails = session.exec(statement).all()
        return [sql_message_to_standard_message(mail) for mail in mails]

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

        with Session(self.engine) as session:
            statement = select(EmailSummarySQL).where(
                EmailSummarySQL.email_message_id == email_id
            )
            summary = session.exec(statement).first()

        if summary is None:
            return None

        return summary.summary_text

    def get_mail_chat(self, email_id: str) -> Optional[EmailChat]:

        with Session(self.engine) as session:
            statement = select(EmailChatSQL).where(
                EmailChatSQL.email_message_id == email_id
            )
            summary = session.exec(statement).first()

        if summary is None:
            return None

        return sql_email_chat_to_email_chat(summary)
