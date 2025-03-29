import json
from typing import List, Optional

from ollama import chat
from sqlmodel import Field, SQLModel

from .chats import EmailChat
from .config import DRAFT_GENERATOR_MODEL_NAME


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


def generate_draft_with_ollama(
    message_id: str,
    current_chat: EmailChat,
    context_chats: List[EmailChat] = [],
    previous_drafts: List[EmailDraftSQL] = [],
    current_version: int = 1,
) -> EmailDraftSQL:
    """
    Generates an email draft using an LLM via Ollama.

    The prompt instructs the model as follows:
      - Begin with the current chat context (for strong attention).
      - Then include additional contextual chats.
      - Then list previous draft versions if available, instructing the model to incorporate user change wishes.
      - Finally, instruct to generate a single, refined draft reply that respects the style and tonality.

    Returns only a single string draft.
    """
    prompt_parts = []

    # Instruction to the model
    prompt_parts.append(
        "You are an AI assistant tasked with generating a new draft of an email."
    )
    prompt_parts.append(
        "The goal is to create a well-written and appropriate response to the latest message in the provided chat history."
    )

    # Render previous drafts if they exist
    if previous_drafts:
        prompt_parts.append("\n--- Previous Drafts ---")
        sorted_drafts = sorted(previous_drafts, key=lambda d: d.version_number)
        for draft in sorted_drafts:
            prompt_parts.append(draft.format_for_llm())
        prompt_parts.append(
            "\nBased on the previous drafts, please incorporate any feedback or changes the user might have implied. Focus on refining the content and addressing any potential issues."
        )
    else:
        prompt_parts.append(
            "\nThis is the first draft. Please generate a complete and appropriate response based on the chat history."
        )

    # Render the current chat context first
    prompt_parts.append("\n--- Current Chat History ---")
    prompt_parts.append(current_chat.format_chat_for_llm())
    prompt_parts.append(
        "\nThe last message in this chat is the one that needs a response."
    )

    # Include additional context chats if available
    if context_chats:
        prompt_parts.append("\n--- Contextual Chat History ---")
        prompt_parts.append(
            "The following are different chats of the user, maybe even with the same subject, for you to learn the user's style and tonality with the respective subject."
        )
        for context_chat in context_chats:
            prompt_parts.append(context_chat.format_chat_for_llm())

    # Final instruction
    prompt_parts.append("\n--- Task ---")
    prompt_parts.append(
        "Generate a new email draft that responds appropriately to the last message in the 'Current Chat History'."
    )
    prompt_parts.append(
        "Ensure the draft is well-structured, grammatically correct, and maintains the user's style and tonality, taking into account all provided context."
    )

    full_prompt = "\n".join(prompt_parts)

    response = chat(
        model=DRAFT_GENERATOR_MODEL_NAME,
        messages=[{"role": "user", "content": full_prompt}],
    )

    draft_text = response.message.content.strip()
    return EmailDraftSQL(
        message_id=message_id,
        version_number=current_version,
        draft_text=draft_text,
        by_user=False,
    )
