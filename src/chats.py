from ollama import chat
from pydantic import BaseModel
from datetime import datetime
from typing import List


class ChatEntry(BaseModel):
    author: str
    date_sent: datetime
    enty_content: str


class EmailChat(BaseModel):
    entries: List[ChatEntry]


def generate_email_chat_with_ollama(email_text: str, model: str) -> EmailChat:

    response = chat(
        model=model,
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
                    f"<mailContent>{email_text}</mailContent>"
                ),
            }
        ],
        format=EmailChat.model_json_schema(),
    )

    return EmailChat.model_validate_json(response.message.content)
