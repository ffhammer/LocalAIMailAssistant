import email.utils
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, EmailStr
from sqlmodel import Field, SQLModel


class MailMessage(BaseModel):
    id: int
    mailbox: str
    content: str
    date_received: datetime
    date_sent: datetime
    deleted_status: bool
    junk_mail_status: bool
    message_id: str
    reply_to: Optional[str]
    sender: EmailStr
    subject: Optional[str]
    was_replied_to: bool
    seen: bool = False
    answered: bool = False
    flagged: bool = False

    def __eq__(self, other) -> bool:
        if not isinstance(other, MailMessage):
            return NotImplemented
        return self.model_dump() == other.model_dump()


def parse_processed_email(msg: EmailMessage, mailbox: str, uid: int) -> MailMessage:
    def parse_date(d: Optional[str]) -> datetime:
        return datetime(*email.utils.parsedate_tz(d)[:6]) if d else datetime.min

    def get_body(m: EmailMessage) -> str:
        if m.is_multipart():
            for part in m.walk():
                if part.get_content_type() == "text/plain":
                    return part.get_payload(decode=True).decode(errors="replace")
        return m.get_payload(decode=True).decode(errors="replace")

    return MailMessage(
        id=uid,
        mailbox=mailbox,
        content=get_body(msg),
        date_received=parse_date(msg.get("Date")),
        date_sent=parse_date(msg.get("Date")),
        deleted_status="\\Deleted" in msg.get("Flags", ""),
        junk_mail_status="Junk"
        in (msg.get("X-Folder", "") + msg.get("X-Spam-Flag", "")),
        message_id=msg.get("Message-ID", "").strip(),
        reply_to=msg.get("In-Reply-To"),
        sender=email.utils.parseaddr(msg.get("From"))[1],
        subject=msg.get("Subject"),
        was_replied_to=msg.get("In-Reply-To") is not None,
    )


class MailMessageSQL(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    mailbox: str = Field(index=True)
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
    imap_uid: int = Field(index=True)
    seen: bool = False
    answered: bool = False
    flagged: bool = False


def sql_message_to_standard_message(mail: MailMessageSQL) -> MailMessage:
    content = Path(mail.content_file).read_text(encoding="utf-8")
    return MailMessage(
        id=mail.imap_uid,
        mailbox=mail.mailbox,
        content=content,
        date_received=mail.date_received,
        date_sent=mail.date_sent,
        deleted_status=mail.deleted_status,
        junk_mail_status=mail.junk_mail_status,
        message_id=mail.message_id,
        reply_to=mail.reply_to,
        sender=mail.sender,
        subject=mail.subject,
        was_replied_to=mail.was_replied_to,
        seen=mail.seen,
        answered=mail.answered,
        flagged=mail.flagged,
    )
