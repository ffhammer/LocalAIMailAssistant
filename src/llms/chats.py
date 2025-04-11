from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import OllamaLLM
from loguru import logger

from ..models import ChatEntry, EmailChat, MailMessage
from ..settings import LLMSettings, Settings

llm_settings = LLMSettings()
ollama_model = OllamaLLM(model=llm_settings.chat_extractor_moedel)
gemini_model = ChatGoogleGenerativeAI(model=llm_settings.gemini_model)
parser = PydanticOutputParser(pydantic_object=EmailChat)


def generate_default_chat(message: MailMessage) -> EmailChat:
    assert message.reply_to is None
    return EmailChat(
        entries=[
            ChatEntry(
                author=message.sender,
                date_sent=message.date_sent,
                entry_content=message.content,
            )
        ]
    )


def generate_email_chat_with_llm(message: MailMessage, settings: Settings) -> EmailChat:
    assert message.reply_to is not None
    logger.debug(f"using model {settings.llm_provider}")
    model = ollama_model if settings.llm_provider == "ollama" else gemini_model

    prompt = PromptTemplate.from_template(
        "Extract conversation entries from the email reply below. "
        "Return ONLY a valid JSON array with the following fields:\n"
        "- author: sender's email\n"
        "- date_sent: ISO 8601 timestamp\n"
        "- entry_content: message body without quoted text. Include greetings.\n\n"
        "<mailContent>{mail_content}</mailContent>\n\n{format_instructions}",
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    chain = prompt | model | parser
    return chain.invoke({"mail_content": message.content})
