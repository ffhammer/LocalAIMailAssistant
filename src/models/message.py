import email.utils
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from loguru import logger
from pydantic import BaseModel, EmailStr
from sqlmodel import Field, SQLModel


def get_body(m: EmailMessage) -> Optional[str]:
    texts: list[str] = []
    htmls: list[str] = []
    if m.is_multipart():
        for part in m.walk():
            if part.get_content_disposition() == "attachment":
                continue
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            decoded = payload.decode(errors="replace")
            if ctype == "text/plain":
                texts.append(decoded)
            elif ctype == "text/html":
                htmls.append(decoded)
    else:
        ctype = m.get_content_type()
        payload = m.get_payload(decode=True)
        if payload:
            decoded = payload.decode(errors="replace")
            if ctype == "text/plain":
                texts.append(decoded)
            elif ctype == "text/html":
                htmls.append(decoded)

    if texts:
        return "\n".join(texts).strip()
    elif htmls:
        cleaned = [
            BeautifulSoup(html, "html.parser").get_text(separator="\n")
            for html in htmls
        ]
        return "\n".join(cleaned).strip()
    return None


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


def parse_processed_email(
    msg: EmailMessage, mailbox: str, uid: int
) -> Optional[MailMessage]:
    def parse_date(d: Optional[str]) -> datetime:
        return datetime(*email.utils.parsedate_tz(d)[:6]) if d else datetime.min

    body = get_body(msg)
    if body is None:
        logger.debug("could not extraxt body")
        return None

    return MailMessage(
        id=uid,
        mailbox=mailbox,
        content=body,
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
