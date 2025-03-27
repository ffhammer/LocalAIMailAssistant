from ollama import chat

from .chats import EmailChat
from .config import SUMMARY_MODEL


def generate_summary(email_chat: EmailChat) -> str:
    prompt = (
        "You are given an email chat in JSON format, which includes a 'chat' array of messages "
        "and an 'instruction' field. Each message in the 'chat' array has 'author', 'date_sent', "
        "'content', and 'focus' (indicating the last message)\n\n"
        "Your task is to generate a concise, single-sentence headline summary that captures the overall context "
        "of the conversation with emphasis on the final message."
        "Do NOT start the summary with phrases like 'The last entry' or any similar wording. "
        "Return ONLY the summary text, without any introductory or concluding phrases.\n\n"
        f"Chat: {email_chat.format_chat_for_llm()}"
        "\nSummary: "
    )

    response = chat(
        model=SUMMARY_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.message.content.strip(' "')
