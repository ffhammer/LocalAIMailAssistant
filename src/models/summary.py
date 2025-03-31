from typing import Optional

from sqlmodel import Field, SQLModel


class EmailSummarySQL(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email_message_id: str = Field(index=True, unique=True)
    summary_text: str
