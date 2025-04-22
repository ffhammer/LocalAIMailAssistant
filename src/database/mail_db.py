from pathlib import Path
from typing import List, Optional, TypeVar

from loguru import logger
from result import Err, Ok, Result
from sqlalchemy.orm import joinedload
from sqlmodel import Session, SQLModel, create_engine, select

from src.models import (
    Attachment,
    EmailChat,
    EmailChatSQL,
    EmailDraftSQL,
    EmailSummarySQL,
    MailFlag,
    MailHeader,
    MailMessage,
    UpdateStatus,
    sql_email_chat_to_email_chat,
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

        self.db_path = self.path / "mail.db"
        self.last_update_info = self.path / "update_info.json"
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        SQLModel.metadata.create_all(self.engine)

    def query_first_item(
        self, table: TABLE_TYPE, *where_clauses
    ) -> Optional[TABLE_TYPE]:
        with Session(self.engine, expire_on_commit=False) as session:
            statement = select(table)
            for clause in where_clauses:
                statement = statement.where(clause)

            return session.exec(statement=statement).first()

    def add_values(self, values: list[TABLE_TYPE]) -> None:
        with Session(self.engine, expire_on_commit=False) as session:
            session.add_all(values)
            session.commit()

    def add_value(self, value: TABLE_TYPE) -> None:
        with Session(self.engine, expire_on_commit=False) as session:
            session.add(value)
            session.commit()

    def save_mail(self, mail: MailMessage, attachments: list[Attachment] = []):
        with Session(self.engine, expire_on_commit=False) as session:
            session.add(mail)
            for attachment in attachments:
                attachment.email = mail
                session.add(attachment)
            session.commit()

    def query_table(self, table_model: SQLModel, *where_clauses) -> List[SQLModel]:
        with Session(self.engine, expire_on_commit=False) as session:
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

    def get_email_by_message_id(self, email_id: str) -> Optional[MailMessage]:
        with Session(self.engine, expire_on_commit=False) as session:
            statement = (
                select(MailMessage)
                .where(MailMessage.message_id == email_id)
                .options(joinedload(MailMessage.attachments))
            )

            return session.exec(statement=statement).first()

    def query_email_headers(self, *where_clauses) -> List[MailHeader]:
        with Session(self.engine, expire_on_commit=False) as session:
            stmt = select(
                MailMessage.message_id,
                MailMessage.sender,
                MailMessage.subject,
                MailMessage.date_sent,
                MailMessage.date_received,
                MailMessage.mailbox,
                MailMessage.seen,
                MailMessage.answered,
                MailMessage.flagged,
                MailMessage.deleted_status,
                MailMessage.was_replied_to,
                MailMessage.junk_mail_status,
                MailMessage.deleted_status,
            )
            for clause in where_clauses:
                stmt = stmt.where(clause)
            rows = session.exec(stmt).mappings().all()
        return [MailHeader.model_validate(row) for row in rows]

    def query_email_ids(self, *where_clauses) -> List[str]:
        return list(self.query_table(MailMessage.message_id, *where_clauses))

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

        with Session(self.engine, expire_on_commit=False) as session:
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
        with Session(self.engine, expire_on_commit=False) as session:
            stmt = select(table_model)
            for clause in where_clauses:
                stmt = stmt.where(clause)
            records = session.exec(stmt).all()
            for record in records:
                session.delete(record)
            session.commit()

    def update_flags(self, data: dict[str, tuple[MailFlag]], mailbox) -> None:
        for uid, flags in data.items():
            mails: list[MailMessage] = self.query_table(
                MailMessage,
                MailMessage.mailbox == mailbox,
                MailMessage.uid == uid,
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

            with Session(self.engine, expire_on_commit=False) as session:
                for mail in mails:
                    session.add(mail)
                session.commit()

    def toggle_flag(
        self, email_message_id: str, flag: MailFlag
    ) -> Result[MailMessage, str]:
        mail: MailMessage = self.query_first_item(
            MailMessage, MailMessage.message_id == email_message_id
        )

        if mail is None:
            return Err(f"can't find mail {email_message_id}")

        if flag == MailFlag.Answered:
            mail.answered = not mail.answered
        if flag == MailFlag.Seen:
            mail.seen = not mail.seen
        if flag == MailFlag.Flagged:
            mail.flagged = not mail.flagged
        if flag == MailFlag.Deleted:
            mail.deleted_status = not mail.deleted_status

        with Session(self.engine, expire_on_commit=False) as session:
            session.add(mail)
            session.commit()

        return Ok(sql_email_chat_to_email_chat(mail))
