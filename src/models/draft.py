import json
from typing import Optional

from sqlmodel import Field, SQLModel


class EmailDraftSQL(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    message_id: str = Field(index=True)
    version_number: int
    draft_text: str
    by_user: bool

    def format_for_llm(self) -> str:
        return json.dumps(
            {
                "version": self.version_number,
                "author": "user" if self.by_user else "llm",
                "content": self.draft_text,
            },
            indent=2,
        )
