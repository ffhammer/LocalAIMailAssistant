from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from email.message import EmailMessage
import email.utils


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
