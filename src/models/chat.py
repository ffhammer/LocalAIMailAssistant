import json
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, model_validator
from sqlmodel import JSON, Column, Field, SQLModel


class ChatEntry(BaseModel):
    author: str
    date_sent: datetime
    entry_content: str


class EmailChat(BaseModel):
    entries: List[ChatEntry]
    authors: list[str]

    @model_validator(mode="before")
    def generate_authors(cls, values):
        if "authors" not in values:
            authors = set()

            for entry in values["entries"]:
                author = (
                    entry.author if isinstance(entry, ChatEntry) else entry["author"]
                )

                if author:
                    authors.add(author)

            values["authors"] = list(authors)
        return values

    def format_chat_for_llm(self) -> str:
        sorted_entries = sorted(self.entries, key=lambda e: e.date_sent)
        formatted = [
            {
                "author": e.author,
                "date_sent": e.date_sent.isoformat(),
                "content": e.entry_content.strip(),
                "focus": i == len(sorted_entries) - 1,
            }
            for i, e in enumerate(sorted_entries)
        ]
        return json.dumps(formatted, indent=2)


class EmailChatSQL(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email_message_id: str = Field(index=True, unique=True)
    chat_json: str
    authors: list[str] = Field(default_factory=list, sa_column=Column(JSON))


def sql_email_chat_to_email_chat(chat: EmailChatSQL) -> EmailChat:
    return EmailChat.model_validate_json(chat.chat_json)
