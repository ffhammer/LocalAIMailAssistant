from typing import List

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import OllamaLLM

from src.models import EmailChat, EmailDraftSQL
from src.settings import LLMSettings, Settings

ollama_model = OllamaLLM(model=LLMSettings().draft_generator_model)
llm_settings = LLMSettings()
ollama_model = OllamaLLM(model=llm_settings.chat_extractor_moedel)
gemini_model = ChatGoogleGenerativeAI(model=llm_settings.gemini_model)
parser = StrOutputParser()


def generate_draft_with_llm(
    message_id: str,
    current_chat: EmailChat,
    settings: Settings,
    context_chats: List[EmailChat] = [],
    previous_drafts: List[EmailDraftSQL] = [],
    current_version: int = 1,
) -> EmailDraftSQL:
    model = ollama_model if settings.llm_provider == "ollama" else gemini_model

    parts = []

    parts.append(
        "You are an AI assistant tasked with generating a new draft of an email."
    )
    parts.append(
        "The goal is to create a well-written and appropriate response to the latest message in the provided chat history."
    )

    if previous_drafts:
        parts.append("\n--- Previous Drafts ---")
        for draft in sorted(previous_drafts, key=lambda d: d.version_number):
            parts.append(draft.format_for_llm())
        parts.append(
            "\nIncorporate any feedback or changes the user might have implied."
        )
    else:
        parts.append("\nThis is the first draft. Please generate a full response.")

    parts.append("\n--- Current Chat History ---")
    parts.append(current_chat.format_chat_for_llm())
    parts.append("\nThe last message needs a response.")

    if context_chats:
        parts.append("\n--- Contextual Chat History ---")
        parts.append("Learn from user's style and tone across related chats.")
        for chat in context_chats:
            parts.append(chat.format_chat_for_llm())

    parts.append("\n--- Task ---")
    parts.append("Generate a draft response to the last message.")
    parts.append("Ensure it's well-structured, correct, and fits the user's style.")

    prompt = PromptTemplate.from_template("{content}")
    chain = prompt | model | parser
    draft_text = chain.invoke({"content": "\n".join(parts)}).strip()

    return EmailDraftSQL(
        message_id=message_id,
        version_number=current_version,
        draft_text=draft_text,
        by_user=False,
    )
