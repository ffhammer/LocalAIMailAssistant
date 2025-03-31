import email.utils
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, EmailStr
from sqlmodel import Field, SQLModel


class MailMessage(BaseModel):
    Id: int
    Mailbox: str
    Content: str
    Date_Received: datetime
    Date_Sent: datetime
    Deleted_Status: bool
    Junk_Mail_Status: bool
    Message_ID: str
    Reply_To: Optional[str]
    Sender: EmailStr
    Subject: Optional[str]
    Was_Replied_To: bool

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
        Id=uid,
        Mailbox=mailbox,
        Content=get_body(msg),
        Date_Received=parse_date(msg.get("Date")),
        Date_Sent=parse_date(msg.get("Date")),
        Deleted_Status="\\Deleted" in msg.get("Flags", ""),
        Junk_Mail_Status="Junk"
        in (msg.get("X-Folder", "") + msg.get("X-Spam-Flag", "")),
        Message_ID=msg.get("Message-ID", "").strip(),
        Reply_To=msg.get("In-Reply-To"),
        Sender=email.utils.parseaddr(msg.get("From"))[1],
        Subject=msg.get("Subject"),
        Was_Replied_To=msg.get("In-Reply-To") is not None,
    )


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
