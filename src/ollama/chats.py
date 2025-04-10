from ollama import chat

from ..config import CHAT_EXTRACTOR_MODEL_NAME
from ..models import ChatEntry, EmailChat, MailMessage


def generate_default_chat(message: MailMessage) -> EmailChat:
    assert message.reply_to is None

    return EmailChat(
        entries=[
            ChatEntry(
                author=message.sender,
                date_sent=message.date_sent,
                enty_content=message.content,
            )
        ]
    )


def generate_email_chat_with_ollama(message: MailMessage) -> EmailChat:
    assert message.reply_to is not None

    response = chat(
        model=CHAT_EXTRACTOR_MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract conversation entries from the email reply below. "
                    "Return ONLY a valid JSON array without any extra text. "
                    "Each entry must have:\n"
                    " - author: sender's email\n"
                    " - date_sent: ISO 8601 timestamp\n"
                    " - entry_content: message body without quoted text. Include the greetings at the start and end if there are any.\n\n"
                    f"<mailContent>{message.content}</mailContent>"
                ),
            }
        ],
        format=EmailChat.model_json_schema(),
    )

    return EmailChat.model_validate_json(response.message.content)
