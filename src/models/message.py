from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr
from sqlmodel import Field, Relationship, SQLModel


class MailHeader(BaseModel):
    message_id: str
    sender: EmailStr
    subject: Optional[str]
    date_sent: datetime
    date_received: datetime
    mailbox: str
    seen: bool
    answered: bool
    flagged: bool
    was_replied_to: bool
    junk_mail_status: bool
    deleted_status: bool


class MailMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    model_config = ConfigDict(from_attributes=True)
    mailbox: str = Field(index=True)
    date_received: datetime
    date_sent: datetime
    deleted_status: bool = False
    junk_mail_status: bool = False
    message_id: str = Field(index=True, unique=True)
    reply_to: Optional[str]
    sender: EmailStr
    subject: Optional[str]
    was_replied_to: bool = False
    uid: int = Field(index=True)
    seen: bool = False
    answered: bool = False
    flagged: bool = False
    display_name_mismatch: bool = False
    dkim_result: Optional[str] = None
    dmarc_result: Optional[str] = None
    plain_text: str
    html_clean: Optional[str] = None
    html_raw: Optional[str] = None
    attachments: list["Attachment"] = Relationship(
        back_populates="email",
    )


class Attachment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email_message_id: Optional[int] = Field(
        default=None, foreign_key="mailmessage.message_id", index=True
    )
    part_id: Optional[str]
    size: int
    possibly_dangerous: int
    filename: str
    path: Optional[str]
    mime_type: str
    email: MailMessage = Relationship(back_populates="attachments")
