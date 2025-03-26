from .config import DRAFT_MODEL
from ollama import chat
from pydantic import BaseModel
from datetime import datetime
from typing import List
from .message import MailMessage


class ChatEntry(BaseModel):
    author: str
    date_sent: datetime
    enty_content: str


class EmailChat(BaseModel):
    entries: List[ChatEntry]


def generate_email_chat_with_ollama(message: MailMessage) -> EmailChat:
    if message.Reply_To is None:
        return EmailChat(
            [
                ChatEntry(
                    author=message.Sender,
                    date_sent=message.Date_Sent,
                    enty_content=message.Content,
                )
            ]
        )

    response = chat(
        model=DRAFT_MODEL,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract conversation entries from the email reply below. "
                    "Return ONLY a valid JSON array without any extra text. "
                    "Each entry must have:\n"
                    " - author: sender's email\n"
                    " - date_sent: ISO 8601 timestamp\n"
                    " - entry_content: message body without quoted text\n\n"
                    f"<mailContent>{message.Content}</mailContent>"
                ),
            }
        ],
        format=EmailChat.model_json_schema(),
    )

    return EmailChat.model_validate_json(response.message.content)
